import re
import logging
from typing import List, Dict, Any
from backend.graph.neo4j_client import neo4j_client
from backend.ingestion.entity_extractor import canonicalize_entity_name, remap_relationship_type, VALID_RELATIONSHIPS

logger = logging.getLogger(__name__)


def clean_property_key(key: str) -> str:
    """Cleans property keys to ensure they are valid Neo4j identifiers."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', key).strip("_")


def _make_canonical_id(name: str) -> str:
    """Creates a stable canonical ID from a name for deduplication."""
    return re.sub(r'[^A-Z0-9]', '', name.upper())


def upsert_entity(entity: Dict[str, Any], doc_id: int, tenant_id: str = "default") -> bool:
    """Inserts or updates an entity node in Neo4j, scoped to a tenant."""
    name = canonicalize_entity_name(entity["name"].strip())
    label = entity["type"]
    confidence = entity.get("confidence", 1.0)
    properties = entity.get("properties", {})
    canonical_id = _make_canonical_id(name)
    aliases = entity.get("aliases", [name])
    extraction_method = entity.get("source", "llm")
    
    subtype = entity.get("subtype")
    subclass = entity.get("subclass")
    if subtype:
        properties["subtype"] = subtype
    if subclass:
        properties["subclass"] = subclass
    
    asset_id = None
    if label == "Equipment":
        match = re.search(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', name)
        if match:
            asset_id = match.group(1)

    if not re.match(r'^[a-zA-Z0-9_]+$', label):
        logger.error(f"Invalid entity label name: {label}")
        return False

    # MERGE on canonical_id to prevent C17/C-17 duplicates
    cypher = f"""
    MERGE (n:{label} {{canonical_id: $canonical_id, tenant_id: $tenant_id}})
    ON CREATE SET n.name = $name,
                  n.aliases = $aliases,
                  n.confidence = $confidence,
                  n.source_doc_id = $source_doc_id,
                  n.extraction_method = $extraction_method,
                  n.created_at = timestamp()
    ON MATCH SET n.aliases = [x IN n.aliases + $aliases WHERE x IS NOT NULL],
                 n.confidence = case when $confidence > n.confidence then $confidence else n.confidence end,
                 n.name = CASE WHEN $confidence > n.confidence THEN $name ELSE n.name END,
                 n.last_updated = timestamp()
    """

    params = {
        "name": name,
        "canonical_id": canonical_id,
        "tenant_id": tenant_id,
        "source_doc_id": doc_id,
        "confidence": confidence,
        "aliases": aliases,
        "extraction_method": extraction_method
    }
    
    if asset_id:
        cypher += "\nSET n.asset_id = $asset_id"
        params["asset_id"] = asset_id

    for k, v in properties.items():
        clean_k = clean_property_key(k)
        if clean_k and clean_k not in ["name", "canonical_id", "source_doc_id", "confidence", "created_at", "tenant_id", "aliases", "extraction_method", "asset_id"]:
            cypher += f"\nSET n.{clean_k} = ${clean_k}"
            params[clean_k] = v

    try:
        neo4j_client.run_query(cypher, params)
        
        # Ontology: create IS_A edges
        if subtype:
            hierarchy_cypher = f"""
            MATCH (n:{label} {{canonical_id: $canonical_id, tenant_id: $tenant_id}})
            MERGE (sub:Subtype {{name: $subtype, tenant_id: $tenant_id}})
            ON CREATE SET sub.created_at = timestamp()
            MERGE (n)-[:IS_A {{tenant_id: $tenant_id}}]->(sub)
            """
            neo4j_client.run_query(hierarchy_cypher, {"canonical_id": canonical_id, "tenant_id": tenant_id, "subtype": subtype})
            
            if subclass:
                subclass_cypher = f"""
                MATCH (sub:Subtype {{name: $subtype, tenant_id: $tenant_id}})
                MERGE (cls:Subclass {{name: $subclass, tenant_id: $tenant_id}})
                ON CREATE SET cls.created_at = timestamp()
                MERGE (sub)-[:IS_A {{tenant_id: $tenant_id}}]->(cls)
                MERGE (n:{label} {{canonical_id: $canonical_id, tenant_id: $tenant_id}})
                MERGE (n)-[:IS_A {{tenant_id: $tenant_id}}]->(cls)
                """
                neo4j_client.run_query(subclass_cypher, {"canonical_id": canonical_id, "tenant_id": tenant_id, "subtype": subtype, "subclass": subclass})
                
        return True
    except Exception as e:
        logger.error(f"Failed to upsert Neo4j node {name} ({label}): {e}")
        return False


def upsert_relationship(rel: Dict[str, Any], doc_id: int, tenant_id: str = "default") -> bool:
    """Inserts or updates a relationship edge in Neo4j, scoped to a tenant."""
    source = canonicalize_entity_name(rel["source"].strip())
    target = canonicalize_entity_name(rel["target"].strip())
    rel_type = remap_relationship_type(rel.get("type", "RELATED_TO"))
    confidence = rel.get("confidence", 1.0)
    extraction_method = rel.get("extraction_method", "llm")

    if confidence < 0.40:
        logger.info(f"Skipping relationship {source} -> {target} due to low confidence ({confidence})")
        return False

    if not re.match(r'^[a-zA-Z0-9_]+$', rel_type):
        logger.error(f"Invalid relationship type after remapping: {rel_type}")
        return False

    source_cid = _make_canonical_id(source)
    target_cid = _make_canonical_id(target)

    # WHERE clause matches by aliases too, not just canonical_name
    cypher = f"""
    MATCH (s {{tenant_id: $tenant_id}})
    WHERE s.canonical_id = $source_cid OR $source IN s.aliases OR s.short_id = $source_cid
    WITH s
    MATCH (t {{tenant_id: $tenant_id}})
    WHERE t.canonical_id = $target_cid OR $target IN t.aliases OR t.short_id = $target_cid
    WITH s, t
    WHERE id(s) <> id(t)
    MERGE (s)-[r:{rel_type}]->(t)
    ON CREATE SET r.source_doc_id = $source_doc_id,
                  r.confidence = $confidence,
                  r.extraction_method = $extraction_method,
                  r.tenant_id = $tenant_id,
                  r.created_at = timestamp(),
                  r.chunk_id = $chunk_id,
                  r.evidence = $evidence,
                  r.event_time = $event_time,
                  r.valid_from = $valid_from,
                  r.valid_to = $valid_to
    ON MATCH SET r.confidence = case when $confidence > r.confidence then $confidence else r.confidence end,
                 r.last_updated = timestamp(),
                 r.event_time = coalesce($event_time, r.event_time),
                 r.valid_from = coalesce($valid_from, r.valid_from),
                 r.valid_to = coalesce($valid_to, r.valid_to),
                 r.evidence = case when $evidence IS NOT NULL AND r.evidence IS NULL then $evidence 
                                   when $evidence IS NOT NULL AND size($evidence) > size(coalesce(r.evidence, "")) then $evidence 
                                   else r.evidence end
    RETURN type(r)
    """

    params = {
        "source": source,
        "target": target,
        "source_cid": source_cid,
        "target_cid": target_cid,
        "tenant_id": tenant_id,
        "source_doc_id": doc_id,
        "confidence": confidence,
        "extraction_method": extraction_method,
        "chunk_id": rel.get("chunk_index"),
        "evidence": rel.get("evidence"),
        "event_time": rel.get("event_time"),
        "valid_from": rel.get("valid_from"),
        "valid_to": rel.get("valid_to")
    }

    try:
        results = neo4j_client.run_query(cypher, params)
        if not results:
            logger.warning(f"Could not create relationship {source} -> {target} (nodes may not exist yet)")
            return False
        return True
    except Exception as e:
        logger.error(f"Failed to upsert Neo4j relationship {source} -[{rel_type}]-> {target}: {e}")
        return False


def batch_upsert_entities(entities: List[Dict[str, Any]], doc_id: int, tenant_id: str = "default") -> int:
    """
    Batch upserts entities using UNWIND grouped by label.
    Merges on canonical_id to prevent duplicates (C-17 == C17).
    """
    if not entities:
        return 0

    seen_canonical = {}
    deduplicated = []
    for entity in entities:
        key = entity["name"].lower().strip()
        if key not in seen_canonical:
            seen_canonical[key] = entity
            deduplicated.append(entity)
        else:
            seen_canonical[key]["aliases"] = list(set(
                seen_canonical[key].get("aliases", []) + entity.get("aliases", [])
            ))

    label_groups: Dict[str, List[Dict]] = {}
    for entity in deduplicated:
        label = entity.get("type", "Equipment")
        if not re.match(r'^[a-zA-Z0-9_]+$', label):
            logger.warning(f"Skipping entity with invalid label: {label}")
            continue
        if label not in label_groups:
            label_groups[label] = []

        name = canonicalize_entity_name(entity["name"].strip())
        
        asset_id = None
        if label == "Equipment":
            match = re.search(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', name)
            if match:
                asset_id = match.group(1)
                
        label_groups[label].append({
            "name": name,
            "canonical_id": _make_canonical_id(name),
            "short_id": _make_canonical_id(entity["name"].strip()),
            "confidence": entity.get("confidence", 1.0),
            "source_doc_id": doc_id,
            "aliases": entity.get("aliases", [name]),
            "extraction_method": entity.get("source", "llm"),
            "asset_id": asset_id,
            "properties": {clean_property_key(k): v for k, v in entity.get("properties", {}).items()
                          if clean_property_key(k) not in ["name", "canonical_id", "source_doc_id", "confidence", "created_at", "tenant_id", "aliases", "extraction_method", "asset_id"]}
        })

    total_created = 0
    for label, entity_batch in label_groups.items():
        cypher = f"""
        UNWIND $entities AS entity
        MERGE (n:{label} {{canonical_id: entity.canonical_id, tenant_id: $tenant_id}})
        ON CREATE SET n.name = entity.name,
                      n.short_id = entity.short_id,
                      n.source_doc_id = entity.source_doc_id,
                      n.confidence = entity.confidence,
                      n.aliases = entity.aliases,
                      n.extraction_method = entity.extraction_method,
                      n.created_at = timestamp()
        ON MATCH SET n.confidence = CASE WHEN entity.confidence > n.confidence THEN entity.confidence ELSE n.confidence END,
                     n.name = CASE WHEN entity.confidence > n.confidence THEN entity.name ELSE n.name END,
                     n.short_id = entity.short_id,
                     n.aliases = [x IN n.aliases + entity.aliases WHERE x IS NOT NULL],
                     n.last_updated = timestamp()
        SET n += entity.properties
        WITH n, entity
        WHERE entity.asset_id IS NOT NULL
        SET n.asset_id = entity.asset_id
        """
        try:
            neo4j_client.run_query(cypher, {"entities": entity_batch, "tenant_id": tenant_id})
            total_created += len(entity_batch)
        except Exception as e:
            logger.warning(f"Batch upsert failed for label {label}, falling back to individual: {e}")
            for entity_data in entity_batch:
                orig = {"name": entity_data["name"], "type": label, "confidence": entity_data["confidence"],
                        "properties": entity_data["properties"], "aliases": entity_data["aliases"], "source": entity_data["extraction_method"]}
                if upsert_entity(orig, doc_id, tenant_id):
                    total_created += 1

    return total_created


def batch_upsert_relationships(relationships: List[Dict[str, Any]], doc_id: int, tenant_id: str = "default") -> int:
    """
    Batch upserts relationships grouped by type using UNWIND.
    Resolves nodes via canonical_id to handle C-17 == C17.
    """
    if not relationships:
        return 0

    type_groups: Dict[str, List[Dict]] = {}
    for rel in relationships:
        rel_type = remap_relationship_type(rel.get("type", "RELATED_TO"))
        if not re.match(r'^[a-zA-Z0-9_]+$', rel_type):
            logger.warning(f"Skipping relationship with invalid type after remapping: {rel_type}")
            continue
        
        confidence = rel.get("confidence", 1.0)
        if confidence < 0.40:
            continue
            
        if rel_type not in type_groups:
            type_groups[rel_type] = []
        source = canonicalize_entity_name(rel["source"].strip())
        target = canonicalize_entity_name(rel["target"].strip())
        type_groups[rel_type].append({
            "source": source,
            "target": target,
            "source_cid": _make_canonical_id(source),
            "target_cid": _make_canonical_id(target),
            "confidence": confidence,
            "extraction_method": rel.get("extraction_method", "llm"),
            "chunk_id": rel.get("chunk_index"),
            "evidence": rel.get("evidence"),
            "event_time": rel.get("event_time"),
            "valid_from": rel.get("valid_from"),
            "valid_to": rel.get("valid_to")
        })

    total_created = 0
    for rel_type, rel_batch in type_groups.items():
        cypher = f"""
        UNWIND $rels AS rel
        MATCH (s {{tenant_id: $tenant_id}})
        WHERE s.canonical_id = rel.source_cid
           OR rel.source IN s.aliases
           OR s.short_id = rel.source_cid
           OR s.canonical_id ENDS WITH rel.source_cid
           OR rel.source_cid ENDS WITH s.canonical_id
        WITH s, rel
        MATCH (t {{tenant_id: $tenant_id}})
        WHERE t.canonical_id = rel.target_cid
           OR rel.target IN t.aliases
           OR t.short_id = rel.target_cid
           OR t.canonical_id ENDS WITH rel.target_cid
           OR rel.target_cid ENDS WITH t.canonical_id
        WITH s, t, rel
        WHERE id(s) <> id(t)
        MERGE (s)-[r:{rel_type}]->(t)
        ON CREATE SET r.source_doc_id = $source_doc_id,
                      r.confidence = rel.confidence,
                      r.extraction_method = rel.extraction_method,
                      r.tenant_id = $tenant_id,
                      r.created_at = timestamp(),
                      r.chunk_id = rel.chunk_id,
                      r.evidence = rel.evidence,
                      r.event_time = rel.event_time,
                      r.valid_from = rel.valid_from,
                      r.valid_to = rel.valid_to
        ON MATCH SET r.confidence = CASE WHEN rel.confidence > r.confidence THEN rel.confidence ELSE r.confidence END,
                     r.last_updated = timestamp(),
                     r.event_time = coalesce(rel.event_time, r.event_time),
                     r.valid_from = coalesce(rel.valid_from, r.valid_from),
                     r.valid_to = coalesce(rel.valid_to, r.valid_to),
                     r.evidence = CASE WHEN rel.evidence IS NOT NULL AND r.evidence IS NULL THEN rel.evidence
                                       WHEN rel.evidence IS NOT NULL AND size(rel.evidence) > size(coalesce(r.evidence, "")) THEN rel.evidence
                                       ELSE r.evidence END
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
                        "type": rel_type, "confidence": rel_data["confidence"], "extraction_method": rel_data["extraction_method"],
                        "chunk_index": rel_data["chunk_id"], "evidence": rel_data["evidence"],
                        "event_time": rel_data.get("event_time"), "valid_from": rel_data.get("valid_from"), "valid_to": rel_data.get("valid_to")}
                if upsert_relationship(orig, doc_id, tenant_id):
                    total_created += 1

    return total_created


def link_cross_document_entities(tenant_id: str = "default") -> int:
    """
    After ingestion, links Equipment/Asset nodes that share the same canonical_id
    across different source documents. Creates RELATED_TO edges between them.
    This resolves cross-document linking (Incident → Equipment → Manual → SOP).
    """
    cypher = """
    MATCH (a:Equipment {tenant_id: $tenant_id})
    MATCH (b:Equipment {tenant_id: $tenant_id})
    WHERE a.canonical_id = b.canonical_id AND id(a) <> id(b) AND NOT (a)-[:RELATED_TO]-(b)
    MERGE (a)-[r:RELATED_TO]->(b)
    ON CREATE SET r.type = 'cross_document_dedup', r.tenant_id = $tenant_id, r.created_at = timestamp()
    RETURN count(r) as count
    """
    try:
        results = neo4j_client.run_query(cypher, {"tenant_id": tenant_id})
        count = results[0]["count"] if results else 0
        logger.info(f"[CrossDocLink] Created {count} cross-document entity links")
        return count
    except Exception as e:
        logger.warning(f"[CrossDocLink] Failed: {e}")
        return 0


def build_graph_from_extraction(entities: List[Dict[str, Any]], relationships: List[Dict[str, Any]], doc_id: int, tenant_id: str = "default") -> Dict[str, int]:
    """
    Builds the knowledge graph by batch upserting entities and relationships,
    then runs a cross-document deduplication pass.
    Returns count of successful creations.
    """
    nodes_created = batch_upsert_entities(entities, doc_id, tenant_id)
    edges_created = batch_upsert_relationships(relationships, doc_id, tenant_id)

    # Cross-document linking pass
    cross_links = link_cross_document_entities(tenant_id)

    return {
        "nodes_created": nodes_created,
        "edges_created": edges_created,
        "cross_doc_links": cross_links
    }
