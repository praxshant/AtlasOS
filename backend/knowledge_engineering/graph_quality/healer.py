import logging
from typing import Dict, Any
from backend.graph.neo4j_client import neo4j_client
from backend.knowledge_engineering.graph_quality.auditor import run_health_audit

logger = logging.getLogger(__name__)


def heal_graph(tenant_id: str = "default") -> Dict[str, Any]:
    """
    V2.5 Self-Healing Graph Engine.
    Runs automated repairs on the Knowledge Graph:
      1. Fill missing confidence scores with a default of 0.5 (unknown).
      2. Tag orphan nodes with a `HAS_KNOWLEDGE_GAP` marker so they surface
         in the Dashboard rather than silently skewing the score.
    Returns a summary of repairs made and a post-heal audit.
    """
    repairs = []

    # 1. Fill missing confidence scores
    try:
        result = neo4j_client.run_query(
            """
            MATCH (n {tenant_id: $tid})
            WHERE n.confidence IS NULL
            SET n.confidence = 0.5, n.confidence_source = 'healer_default'
            RETURN count(n) as patched
            """,
            {"tid": tenant_id}
        )
        patched = result[0]["patched"] if result else 0
        if patched > 0:
            repairs.append(f"Filled confidence score on {patched} nodes (set to 0.5 / unknown)")
            logger.info(f"[Healer] Patched confidence on {patched} nodes for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"[Healer] Failed to patch confidence scores: {e}")

    # 2. Tag orphan nodes with a knowledge gap relationship
    try:
        # Ensure a root KnowledgeGap node exists for orphan parking
        neo4j_client.run_query(
            """
            MERGE (gap:KnowledgeGap {name: 'Orphan_Node_Pool', tenant_id: $tid})
            ON CREATE SET gap.confidence = 1.0, gap.created_by = 'healer'
            """,
            {"tid": tenant_id}
        )

        result = neo4j_client.run_query(
            """
            MATCH (n {tenant_id: $tid})
            WHERE NOT n:KnowledgeGap
              AND NOT (n)-[]-()
            WITH n
            MATCH (gap:KnowledgeGap {name: 'Orphan_Node_Pool', tenant_id: $tid})
            MERGE (n)-[r:HAS_KNOWLEDGE_GAP]->(gap)
            ON CREATE SET r.tenant_id = $tid, r.healed_at = timestamp()
            RETURN count(n) as healed
            """,
            {"tid": tenant_id}
        )
        healed = result[0]["healed"] if result else 0
        if healed > 0:
            repairs.append(f"Connected {healed} orphan nodes to KnowledgeGap pool")
            logger.info(f"[Healer] Healed {healed} orphan nodes for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"[Healer] Failed to heal orphan nodes: {e}")

    # 3. Post-heal audit
    post_audit = run_health_audit(tenant_id)

    return {
        "repairs": repairs,
        "post_heal_audit": post_audit
    }
