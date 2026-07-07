import logging
from typing import Dict, Any, List
from backend.graph.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

class GraphHealthMonitor:
    def __init__(self):
        pass

    def check_orphan_nodes(self, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """Finds nodes that have no relationships."""
        query = """
        MATCH (n)
        WHERE n.tenant_id = $tenant_id AND NOT (n)--()
        RETURN labels(n) AS labels, n.name AS name, n.canonical_id AS canonical_id
        LIMIT 100
        """
        try:
            return neo4j_client.run_query(query, {"tenant_id": tenant_id})
        except Exception as e:
            logger.error(f"Failed to check orphan nodes: {e}")
            return []

    def check_duplicate_names(self, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """Finds distinct nodes that share the exact same canonical_id (dedup bug)."""
        query = """
        MATCH (n)
        WHERE n.tenant_id = $tenant_id AND n.canonical_id IS NOT NULL
        WITH n.canonical_id AS cid, collect(n) AS nodes, count(n) AS c
        WHERE c > 1
        RETURN cid, [node in nodes | node.name] AS names, c AS count
        LIMIT 50
        """
        try:
            return neo4j_client.run_query(query, {"tenant_id": tenant_id})
        except Exception as e:
            logger.error(f"Failed to check duplicate names: {e}")
            return []

    def check_broken_references(self, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """Finds nodes referencing a document ID that doesn't exist in PostgreSQL. (Mock logic returning empty for now)"""
        # A true check would involve querying Postgres for all doc IDs and comparing.
        # For graph-only scope, we just return empty list as placeholder.
        return []

    def check_low_confidence_edges(self, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """Finds relationships where confidence is < 0.5."""
        query = """
        MATCH (n)-[r]->(m)
        WHERE r.tenant_id = $tenant_id AND r.confidence IS NOT NULL AND r.confidence < 0.5
        RETURN n.name AS source, type(r) AS rel_type, m.name AS target, r.confidence AS confidence
        LIMIT 50
        """
        try:
            return neo4j_client.run_query(query, {"tenant_id": tenant_id})
        except Exception as e:
            logger.error(f"Failed to check low confidence edges: {e}")
            return []

    def check_isolated_clusters(self, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """Uses Louvain to find communities of size 1 or 2."""
        try:
            from backend.graph.graph_analytics import graph_analytics
            communities = graph_analytics.detect_communities(tenant_id)
            isolated = [c for c in communities if len(c["members"]) <= 2]
            return isolated[:20]
        except Exception as e:
            logger.error(f"Failed to check isolated clusters: {e}")
            return []

    def generate_health_report(self, tenant_id: str = "default") -> Dict[str, Any]:
        """Runs all checks and compiles a health report."""
        orphans = self.check_orphan_nodes(tenant_id)
        duplicates = self.check_duplicate_names(tenant_id)
        low_confidence = self.check_low_confidence_edges(tenant_id)
        isolated = self.check_isolated_clusters(tenant_id)
        
        return {
            "orphan_nodes": {
                "count": len(orphans),
                "samples": orphans[:10]
            },
            "duplicate_names": {
                "count": len(duplicates),
                "samples": duplicates[:10]
            },
            "low_confidence_edges": {
                "count": len(low_confidence),
                "samples": low_confidence[:10]
            },
            "isolated_clusters": {
                "count": len(isolated),
                "samples": isolated[:10]
            }
        }

graph_health_monitor = GraphHealthMonitor()
