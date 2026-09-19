import logging
from typing import Dict, Any
from backend.graph.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

def run_health_audit(tenant_id: str = "default") -> Dict[str, Any]:
    """
    V2 Graph Quality Auditor
    Runs a suite of Cypher queries to evaluate the integrity and quality of the Knowledge Graph.
    """
    issues = []
    total_nodes = 0
    total_edges = 0
    
    try:
        # 1. Basic Stats
        res_stats = neo4j_client.run_query(
            "MATCH (n {tenant_id: $tid}) OPTIONAL MATCH (n)-[r]->() RETURN count(distinct n) as nodes, count(r) as edges",
            {"tid": tenant_id}
        )
        if res_stats:
            total_nodes = res_stats[0]["nodes"]
            total_edges = res_stats[0]["edges"]
            
        if total_nodes == 0:
            return {"health_score": 100, "issues": ["Graph is empty"], "metrics": {"nodes": 0, "edges": 0}}

        # 2. Orphan Nodes
        res_orphans = neo4j_client.run_query(
            "MATCH (n {tenant_id: $tid}) WHERE NOT (n)-[]-() RETURN count(n) as orphans",
            {"tid": tenant_id}
        )
        orphans = res_orphans[0]["orphans"] if res_orphans else 0
        if orphans > 0:
            issues.append(f"{orphans} Orphan Nodes (disconnected from the graph)")
            
        # 4. Legacy REL edges (from V1)
        res_legacy_rels = neo4j_client.run_query(
            "MATCH ()-[r:REL {tenant_id: $tid}]->() RETURN count(r) as legacy",
            {"tid": tenant_id}
        )
        legacy = res_legacy_rels[0]["legacy"] if res_legacy_rels else 0
        if legacy > 0:
            issues.append(f"{legacy} Edges are using the V1 generic 'REL' type")
            
        # 3. Unknown Relationships (failed ontology)
        res_unknown_rels = neo4j_client.run_query(
            "MATCH ()-[r:UNKNOWN_RELATIONSHIP {tenant_id: $tid}]->() RETURN count(r) as unknown_rels",
            {"tid": tenant_id}
        )
        unknown_rels = res_unknown_rels[0]["unknown_rels"] if res_unknown_rels else 0
        if unknown_rels > 0:
            issues.append(f"{unknown_rels} Edges failed ontology validation (UNKNOWN_RELATIONSHIP)")

        # 5. Missing Confidence Scores
        res_no_conf = neo4j_client.run_query(
            "MATCH (n {tenant_id: $tid}) WHERE n.confidence IS NULL RETURN count(n) as missing_conf",
            {"tid": tenant_id}
        )
        missing_conf = res_no_conf[0]["missing_conf"] if res_no_conf else 0
        if missing_conf > 0:
            issues.append(f"{missing_conf} Nodes are missing confidence scores")
            
        # Calculate Health Score (Max 100)
        penalty = 0
        penalty += (orphans / total_nodes * 100) if total_nodes > 0 else 0
        penalty += (unknown_rels / total_edges * 100) if total_edges > 0 else 0
        penalty += (legacy / total_edges * 50) if total_edges > 0 else 0
        penalty += (missing_conf / total_nodes * 20) if total_nodes > 0 else 0
        
        health_score = max(0, min(100, int(100 - penalty)))
        
        return {
            "health_score": health_score,
            "issues": issues,
            "metrics": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "orphans": orphans,
                "unknown_relationships": unknown_rels,
                "legacy_relationships": legacy,
                "missing_confidence": missing_conf
            }
        }
    except Exception as e:
        logger.error(f"Graph Audit failed: {e}")
        return {"health_score": 0, "error": str(e)}
