import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.db.postgres import SessionLocal, Document, Chunk, Entity
from backend.vector.qdrant_client import qdrant_client
from backend.graph.neo4j_client import neo4j_client
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def verify_graph_integrity(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Cross-verifies the integrity of data across PostgreSQL, Qdrant, and Neo4j.
    If tenant_id is provided, scopes the check to that tenant.
    Returns a structured report of any discrepancies found.
    """
    db: Session = SessionLocal()
    report = {
        "status": "healthy",
        "tenant_scoped": tenant_id is not None,
        "tenant_id": tenant_id,
        "discrepancies": [],
        "metrics": {}
    }

    try:
        # 1. Gather PostgreSQL Metrics
        doc_query = db.query(Document).filter(Document.status == "completed")
        chunk_query = db.query(Chunk)
        entity_query = db.query(Entity)

        if tenant_id:
            doc_query = doc_query.filter(Document.tenant_id == tenant_id)
            chunk_query = chunk_query.filter(Chunk.tenant_id == tenant_id)
            entity_query = entity_query.filter(Entity.tenant_id == tenant_id)

        pg_docs = doc_query.count()
        pg_chunks = chunk_query.count()
        pg_entities = entity_query.count()
        
        # Get unique canonical names in Postgres for the tenant
        if tenant_id:
            pg_entity_names = {e.canonical_name for e in entity_query.all()}
        else:
            pg_entity_names = {e.canonical_name for e in entity_query.all()}

        report["metrics"]["postgres"] = {
            "completed_documents": pg_docs,
            "chunks": pg_chunks,
            "entities": pg_entities
        }

        # 2. Gather Qdrant Metrics
        collection = settings.QDRANT_COLLECTION_NAME
        try:
            client = qdrant_client.get_client()
            q_info = client.get_collection(collection_name=collection)
            q_vectors = q_info.points_count
            
            # Since Qdrant doesn't easily return a filtered count without a scroll API, 
            # we'll approximate or just rely on total points if no tenant_id is supplied.
            # If tenant_id is provided, we use the scroll API to count accurately (up to a limit).
            if tenant_id:
                # Using scroll to count is expensive, but for integrity checks it's acceptable.
                # We can do a count request if qdrant-client supports it.
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                count_result = client.count(
                    collection_name=collection,
                    count_filter=Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))])
                )
                q_vectors_tenant = count_result.count
            else:
                q_vectors_tenant = q_vectors
                
            report["metrics"]["qdrant"] = {
                "vectors": q_vectors_tenant,
                "total_collection_vectors": q_vectors
            }
            
            if q_vectors_tenant < pg_chunks:
                report["discrepancies"].append(
                    f"Qdrant missing vectors: {pg_chunks} chunks in PG but only {q_vectors_tenant} vectors in Qdrant."
                )
            elif q_vectors_tenant > pg_chunks:
                report["discrepancies"].append(
                    f"Orphaned vectors in Qdrant: {q_vectors_tenant} vectors but only {pg_chunks} chunks in PG."
                )

        except Exception as e:
            logger.error(f"Integrity check: Qdrant error: {e}")
            report["discrepancies"].append(f"Qdrant unreachable or error: {str(e)}")
            report["metrics"]["qdrant"] = {"error": str(e)}

        # 3. Gather Neo4j Metrics
        try:
            neo4j_nodes = 0
            if tenant_id:
                res = neo4j_client.run_query("MATCH (n) WHERE n.tenant_id = $tid AND NOT n:KnowledgeGap AND NOT n:MissingCategory AND NOT n:Subtype AND NOT n:Subclass RETURN count(n) as count, collect(n.name) as names", {"tid": tenant_id})
            else:
                res = neo4j_client.run_query("MATCH (n) WHERE NOT n:KnowledgeGap AND NOT n:MissingCategory AND NOT n:Subtype AND NOT n:Subclass RETURN count(n) as count, collect(n.name) as names")
                
            if res:
                neo4j_nodes = res[0]["count"]
                neo4j_names = set([n for n in res[0]["names"] if n])
            else:
                neo4j_names = set()
                
            report["metrics"]["neo4j"] = {
                "nodes": neo4j_nodes
            }

            # Check for severe desynchronization (like data wipe)
            if pg_entities > 0 and neo4j_nodes == 0:
                msg = f"SEVERE DESYNC: {pg_entities} entities in PostgreSQL but 0 nodes in Neo4j. Graph wipe detected. Recovery is available."
                report["discrepancies"].append(msg)
                report["status"] = "degraded"
            elif neo4j_nodes < pg_entities:
                missing = pg_entities - neo4j_nodes
                report["discrepancies"].append(f"Graph Integrity Check Failed: {missing} entities missing from Neo4j (PG: {pg_entities}, Neo4j: {neo4j_nodes}).")
                
            # Orphaned nodes check (nodes in graph but not in PG)
            orphans = neo4j_names - pg_entity_names
            if orphans and len(orphans) < 100:  # don't spam if too many
                report["metrics"]["neo4j"]["orphaned_nodes_sample"] = list(orphans)[:10]
                report["discrepancies"].append(f"Orphaned graph nodes found: {len(orphans)} nodes exist in Neo4j but not in Postgres.")

        except Exception as e:
            logger.error(f"Integrity check: Neo4j error: {e}")
            report["discrepancies"].append(f"Neo4j unreachable or error: {str(e)}")
            report["metrics"]["neo4j"] = {"error": str(e)}

    except Exception as e:
        logger.error(f"Fatal error during integrity check: {e}")
        report["status"] = "error"
        report["error"] = str(e)
    finally:
        db.close()

    if report["discrepancies"]:
        if report["status"] != "error":
            report["status"] = "degraded"
        logger.warning(f"Graph Integrity Check completed with {len(report['discrepancies'])} discrepancies.")
        for d in report["discrepancies"]:
            logger.warning(f" - {d}")
    else:
        logger.info("Graph Integrity Check passed successfully. Databases are synchronized.")

    return report
