import re
import logging
from typing import List, Dict, Any
from backend.graph.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

def clean_property_key(key: str) -> str:
    """
    Cleans property keys to ensure they are valid Neo4j identifiers.
    """
    return re.sub(r'[^a-zA-Z0-9_]', '_', key).strip("_")

def upsert_entity(entity: Dict[str, Any], doc_id: int, tenant_id: str = "default") -> bool:
    """
    Inserts or updates an entity node in Neo4j, scoped to a tenant.
    """
    name = entity["name"].strip()
    label = entity["type"]
    confidence = entity.get("confidence", 1.0)
    properties = entity.get("properties", {})

    # Construct the Cypher query dynamically for the label
    # We must sanitize the label to prevent Cypher injection
    if not re.match(r'^[a-zA-Z0-9_]+$', label):
        logger.error(f"Invalid entity label name: {label}")
        return False

    # Base MERGE query — scoped to tenant
    cypher = f"""
    MERGE (n:{label} {{name: $name, tenant_id: $tenant_id}})
    ON CREATE SET n.source_doc_id = $source_doc_id,
                  n.confidence = $confidence,
                  n.created_at = timestamp()
    ON MATCH SET n.confidence = case when $confidence > n.confidence then $confidence else n.confidence end
    """

    params = {
        "name": name,
        "tenant_id": tenant_id,
        "source_doc_id": doc_id,
        "confidence": confidence
    }

    # Append extra properties dynamically
    for k, v in properties.items():
        clean_k = clean_property_key(k)
        if clean_k and clean_k not in ["name", "source_doc_id", "confidence", "created_at", "tenant_id"]:
            cypher += f"\nSET n.{clean_k} = ${clean_k}"
            params[clean_k] = v

    try:
        neo4j_client.run_query(cypher, params)
        return True
    except Exception as e:
        logger.error(f"Failed to upsert Neo4j node {name} ({label}): {e}")
        return False

def upsert_relationship(rel: Dict[str, Any], doc_id: int, tenant_id: str = "default") -> bool:
    """
    Inserts or updates a relationship edge in Neo4j, scoped to a tenant.
    """
    source = rel["source"].strip()
    target = rel["target"].strip()
    rel_type = rel["type"]
    confidence = rel.get("confidence", 1.0)

    # Sanitize relationship type
    if not re.match(r'^[a-zA-Z0-9_]+$', rel_type):
        logger.error(f"Invalid relationship type: {rel_type}")
        return False

    cypher = f"""
    MATCH (s {{name: $source, tenant_id: $tenant_id}})
    MATCH (t {{name: $target, tenant_id: $tenant_id}})
    MERGE (s)-[r:{rel_type}]->(t)
    ON CREATE SET r.source_doc_id = $source_doc_id,
                  r.confidence = $confidence,
                  r.tenant_id = $tenant_id,
                  r.created_at = timestamp()
    ON MATCH SET r.confidence = case when $confidence > r.confidence then $confidence else r.confidence end
    RETURN type(r)
    """

    params = {
        "source": source,
        "target": target,
        "tenant_id": tenant_id,
        "source_doc_id": doc_id,
        "confidence": confidence
    }

    try:
        results = neo4j_client.run_query(cypher, params)
        if not results:
            # If source or target node doesn't exist, we can't draw the edge.
            # Usually source and target should have been created in upsert_entity step.
            logger.warning(f"Could not create relationship {source} -> {target} because one of the nodes is missing.")
            return False
        return True
    except Exception as e:
        logger.error(f"Failed to upsert Neo4j relationship {source} -[{rel_type}]-> {target}: {e}")
        return False

def batch_upsert_entities(entities: List[Dict[str, Any]], doc_id: int, tenant_id: str = "default") -> int:
    """
    Batch upserts entities using UNWIND for O(1) round-trips instead of O(N).
    Falls back to individual upserts if batch fails (due to mixed labels).
    """
    if not entities:
        return 0

    # Group entities by label for batch MERGE (Neo4j requires static labels in MERGE)
    label_groups: Dict[str, List[Dict]] = {}
    for entity in entities:
        label = entity.get("type", "Entity")
        if not re.match(r'^[a-zA-Z0-9_]+$', label):
            logger.warning(f"Skipping entity with invalid label: {label}")
            continue
        if label not in label_groups:
            label_groups[label] = []
        label_groups[label].append({
            "name": entity["name"].strip(),
            "confidence": entity.get("confidence", 1.0),
            "source_doc_id": doc_id,
            "properties": {clean_property_key(k): v for k, v in entity.get("properties", {}).items()
                          if clean_property_key(k) not in ["name", "source_doc_id", "confidence", "created_at", "tenant_id"]}
        })

    total_created = 0
    for label, entity_batch in label_groups.items():
        cypher = f"""
        UNWIND $entities AS entity
        MERGE (n:{label} {{name: entity.name, tenant_id: $tenant_id}})
        ON CREATE SET n.source_doc_id = entity.source_doc_id,
                      n.confidence = entity.confidence,
                      n.created_at = timestamp()
        ON MATCH SET n.confidence = CASE WHEN entity.confidence > n.confidence THEN entity.confidence ELSE n.confidence END
        SET n += entity.properties
        """
        try:
            neo4j_client.run_query(cypher, {"entities": entity_batch, "tenant_id": tenant_id})
            total_created += len(entity_batch)
        except Exception as e:
            logger.warning(f"Batch upsert failed for label {label}, falling back to individual: {e}")
            for entity_data in entity_batch:
                orig = {"name": entity_data["name"], "type": label, "confidence": entity_data["confidence"],
                        "properties": entity_data["properties"]}
                if upsert_entity(orig, doc_id, tenant_id):
                    total_created += 1

    return total_created

def batch_upsert_relationships(relationships: List[Dict[str, Any]], doc_id: int, tenant_id: str = "default") -> int:
    """
    Batch upserts relationships grouped by type using UNWIND.
    """
    if not relationships:
        return 0

    # Group by relationship type
    type_groups: Dict[str, List[Dict]] = {}
    for rel in relationships:
        rel_type = rel.get("type", "RELATED_TO")
        if not re.match(r'^[a-zA-Z0-9_]+$', rel_type):
            logger.warning(f"Skipping relationship with invalid type: {rel_type}")
            continue
        if rel_type not in type_groups:
            type_groups[rel_type] = []
        type_groups[rel_type].append({
            "source": rel["source"].strip(),
            "target": rel["target"].strip(),
            "confidence": rel.get("confidence", 1.0)
        })

    total_created = 0
    for rel_type, rel_batch in type_groups.items():
        cypher = f"""
        UNWIND $rels AS rel
        MATCH (s {{name: rel.source, tenant_id: $tenant_id}})
        MATCH (t {{name: rel.target, tenant_id: $tenant_id}})
        MERGE (s)-[r:{rel_type}]->(t)
        ON CREATE SET r.source_doc_id = $source_doc_id,
                      r.confidence = rel.confidence,
                      r.tenant_id = $tenant_id,
                      r.created_at = timestamp()
        ON MATCH SET r.confidence = CASE WHEN rel.confidence > r.confidence THEN rel.confidence ELSE r.confidence END
        RETURN count(r) as count
        """
        try:
            results = neo4j_client.run_query(cypher, {
                "rels": rel_batch,
                "tenant_id": tenant_id,
                "source_doc_id": doc_id
            })
            count = results[0]["count"] if results else 0
            total_created += count
        except Exception as e:
            logger.warning(f"Batch upsert failed for rel type {rel_type}, falling back: {e}")
            for rel_data in rel_batch:
                orig = {"source": rel_data["source"], "target": rel_data["target"],
                        "type": rel_type, "confidence": rel_data["confidence"]}
                if upsert_relationship(orig, doc_id, tenant_id):
                    total_created += 1

    return total_created

def build_graph_from_extraction(entities: List[Dict[str, Any]], relationships: List[Dict[str, Any]], doc_id: int, tenant_id: str = "default") -> Dict[str, int]:
    """
    Builds the graph by batch upserting all entities and relationships, scoped to tenant.
    Uses UNWIND for optimal performance at scale.
    Returns count of successful creations.
    """
    # Use batch operations for scale
    nodes_created = batch_upsert_entities(entities, doc_id, tenant_id)
    edges_created = batch_upsert_relationships(relationships, doc_id, tenant_id)

    return {
        "nodes_created": nodes_created,
        "edges_created": edges_created
    }
