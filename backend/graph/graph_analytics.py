import logging
from typing import List, Dict, Any
from backend.graph.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

class GraphAnalytics:
    def __init__(self):
        pass

    def run_pagerank(self, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """
        Runs PageRank on Equipment nodes to identify critical assets.
        Creates an in-memory graph projection, runs the algorithm, and drops it.
        """
        projection_name = f"equipment_pagerank_{tenant_id}"
        
        # 1. Drop if exists
        try:
            neo4j_client.run_query("CALL gds.graph.drop($name, false)", {"name": projection_name})
        except Exception:
            pass
            
        # 2. Create projection
        cypher_project = """
        CALL gds.graph.project(
            $name,
            'Equipment',
            ['FEEDS', 'SUPPLIES', 'CAUSED_BY', 'AFFECTED_BY', 'CONNECTED_TO']
        )
        """
        try:
            neo4j_client.run_query(cypher_project, {"name": projection_name})
            
            # 3. Run algorithm
            cypher_algo = """
            CALL gds.pageRank.stream($name)
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).name AS name, score
            ORDER BY score DESC
            LIMIT 50
            """
            results = neo4j_client.run_query(cypher_algo, {"name": projection_name})
            return results
        except Exception as e:
            logger.error(f"PageRank failed: {e}")
            return []
        finally:
            try:
                neo4j_client.run_query("CALL gds.graph.drop($name, false)", {"name": projection_name})
            except Exception:
                pass

    def detect_communities(self, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """
        Runs Louvain community detection to group equipment into subsystems.
        """
        projection_name = f"equipment_louvain_{tenant_id}"
        
        try:
            neo4j_client.run_query("CALL gds.graph.drop($name, false)", {"name": projection_name})
        except Exception:
            pass
            
        cypher_project = """
        CALL gds.graph.project(
            $name,
            'Equipment',
            ['FEEDS', 'SUPPLIES', 'CONNECTED_TO']
        )
        """
        try:
            neo4j_client.run_query(cypher_project, {"name": projection_name})
            
            cypher_algo = """
            CALL gds.louvain.stream($name)
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).name AS name, communityId
            ORDER BY communityId
            """
            results = neo4j_client.run_query(cypher_algo, {"name": projection_name})
            
            # Group by community
            communities = {}
            for r in results:
                cid = r["communityId"]
                name = r["name"]
                if cid not in communities:
                    communities[cid] = []
                communities[cid].append(name)
                
            return [{"community": k, "members": v} for k, v in communities.items()]
        except Exception as e:
            logger.error(f"Louvain failed: {e}")
            return []
        finally:
            try:
                neo4j_client.run_query("CALL gds.graph.drop($name, false)", {"name": projection_name})
            except Exception:
                pass

    def get_failure_paths(self, source_name: str, target_name: str, tenant_id: str = "default", k: int = 3) -> List[Dict[str, Any]]:
        """
        Finds K-shortest paths between a source (incident/failure) and target (asset/root cause).
        """
        projection_name = f"failure_paths_{tenant_id}"
        
        try:
            neo4j_client.run_query("CALL gds.graph.drop($name, false)", {"name": projection_name})
        except Exception:
            pass
            
        cypher_project = """
        CALL gds.graph.project(
            $name,
            ['Incident', 'Equipment', 'FailureMode', 'Component'],
            ['CAUSED_BY', 'RESULTED_IN', 'AFFECTED_BY', 'FAILED']
        )
        """
        try:
            neo4j_client.run_query(cypher_project, {"name": projection_name})
            
            cypher_algo = """
            MATCH (source {name: $source_name}), (target {name: $target_name})
            CALL gds.shortestPath.yens.stream(
                $name,
                {
                    sourceNode: source,
                    targetNode: target,
                    k: $k
                }
            )
            YIELD index, sourceNode, targetNode, totalCost, nodeIds, costs, path
            RETURN
                index,
                [node in nodes(path) | node.name] AS node_names,
                totalCost
            ORDER BY index
            """
            results = neo4j_client.run_query(cypher_algo, {
                "name": projection_name,
                "source_name": source_name,
                "target_name": target_name,
                "k": k
            })
            return results
        except Exception as e:
            logger.error(f"Yen's K-Shortest Paths failed: {e}")
            
            # Fallback to standard Cypher shortestPath if GDS is missing/fails
            fallback_query = """
            MATCH (start {name: $source_name}), (end {name: $target_name})
            MATCH p = shortestPath((start)-[*..5]-(end))
            RETURN [node in nodes(p) | node.name] AS node_names, length(p) AS totalCost
            """
            try:
                res = neo4j_client.run_query(fallback_query, {
                    "source_name": source_name,
                    "target_name": target_name
                })
                return [{"index": 0, "node_names": r["node_names"], "totalCost": r["totalCost"]} for r in res]
            except Exception as e2:
                logger.error(f"Fallback shortestPath failed: {e2}")
                return []
        finally:
            try:
                neo4j_client.run_query("CALL gds.graph.drop($name, false)", {"name": projection_name})
            except Exception:
                pass

    def get_similar_equipment(self, equipment_name: str, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """
        Uses Node Similarity to find assets with similar topologies/relationships.
        """
        projection_name = f"equipment_sim_{tenant_id}"
        
        try:
            neo4j_client.run_query("CALL gds.graph.drop($name, false)", {"name": projection_name})
        except Exception:
            pass
            
        cypher_project = """
        CALL gds.graph.project(
            $name,
            ['Equipment', 'FailureMode', 'Procedure', 'Person'],
            ['MAINTAINED_BY', 'HAS_FAILURE_MODE', 'PREVENTS', 'APPLIES_TO']
        )
        """
        try:
            neo4j_client.run_query(cypher_project, {"name": projection_name})
            
            cypher_algo = """
            CALL gds.nodeSimilarity.stream($name)
            YIELD node1, node2, similarity
            WITH gds.util.asNode(node1) AS n1, gds.util.asNode(node2) AS n2, similarity
            WHERE n1.name = $eq_name AND 'Equipment' IN labels(n2)
            RETURN n2.name AS similar_equipment, similarity
            ORDER BY similarity DESC
            LIMIT 5
            """
            results = neo4j_client.run_query(cypher_algo, {
                "name": projection_name,
                "eq_name": equipment_name
            })
            return results
        except Exception as e:
            logger.error(f"Node Similarity failed: {e}")
            return []
        finally:
            try:
                neo4j_client.run_query("CALL gds.graph.drop($name, false)", {"name": projection_name})
            except Exception:
                pass

graph_analytics = GraphAnalytics()
