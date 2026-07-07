import time
from typing import Dict, Any

from backend.graph.neo4j_client import neo4j_client

def run_graph_eval(tenant_id: str) -> Dict[str, Any]:
    metrics = {}
    
    try:
        # Total Nodes
        res = neo4j_client.run_query("MATCH (n:Entity {tenant_id: $t}) RETURN count(n) as count", {"t": tenant_id})
        total_nodes = res[0]["count"] if res else 0
        metrics["total_nodes"] = total_nodes
        
        # Total Edges
        res = neo4j_client.run_query("MATCH (n:Entity {tenant_id: $t})-[r]->(m:Entity {tenant_id: $t}) RETURN count(r) as count", {"t": tenant_id})
        total_edges = res[0]["count"] if res else 0
        metrics["total_edges"] = total_edges
        
        # Density
        if total_nodes > 1:
            metrics["density"] = total_edges / (total_nodes * (total_nodes - 1))
        else:
            metrics["density"] = 0
            
        # Orphan Ratio
        res = neo4j_client.run_query("MATCH (n:Entity {tenant_id: $t}) WHERE NOT (n)-[]-() RETURN count(n) as count", {"t": tenant_id})
        orphans = res[0]["count"] if res else 0
        metrics["orphan_ratio"] = orphans / total_nodes if total_nodes else 0
        
        # Avg Degree
        metrics["avg_degree"] = (2 * total_edges) / total_nodes if total_nodes else 0
        
        # Duplicate Ratio (Nodes with same name and label)
        res = neo4j_client.run_query("""
            MATCH (n:Entity {tenant_id: $t})
            WITH n.name as name, labels(n) as lbls, count(*) as count
            WHERE count > 1
            RETURN sum(count) as duplicate_count
        """, {"t": tenant_id})
        duplicates = res[0]["duplicate_count"] if res and res[0]["duplicate_count"] else 0
        metrics["duplicate_ratio"] = duplicates / total_nodes if total_nodes else 0
        
        # IS_A Coverage (Entities with an IS_A relationship out)
        res = neo4j_client.run_query("MATCH (n:Entity {tenant_id: $t})-[r:IS_A]->() RETURN count(DISTINCT n) as count", {"t": tenant_id})
        isa_count = res[0]["count"] if res else 0
        metrics["isa_coverage"] = isa_count / total_nodes if total_nodes else 0
        
    except Exception as e:
        metrics["error"] = str(e)
        
    return metrics
