import networkx as nx
from typing import Dict, Any, List, Optional
import community as community_louvain
from backend.graph.neo4j_client import Neo4jClient
import logging

logger = logging.getLogger(__name__)

class GraphAnalyticsService:
    def __init__(self):
        self.neo4j = Neo4jClient()

    def fetch_full_graph(self) -> nx.DiGraph:
        """Fetches the full Neo4j graph into a NetworkX DiGraph."""
        query = """
        MATCH (n)
        OPTIONAL MATCH (n)-[r]->(m)
        RETURN elementId(n) AS source_id, labels(n)[0] AS source_label, properties(n) AS source_props,
               type(r) AS rel_type, properties(r) AS rel_props,
               elementId(m) AS target_id, labels(m)[0] AS target_label, properties(m) AS target_props
        """
        results = self.neo4j.run_query(query)
        
        G = nx.DiGraph()
        for record in results:
            src_id = record.get("source_id")
            if src_id and not G.has_node(src_id):
                G.add_node(src_id, label=record.get("source_label"), **(record.get("source_props") or {}))
                
            tgt_id = record.get("target_id")
            if tgt_id and not G.has_node(tgt_id):
                G.add_node(tgt_id, label=record.get("target_label"), **(record.get("target_props") or {}))
                
            if src_id and tgt_id:
                rel_type = record.get("rel_type")
                G.add_edge(src_id, tgt_id, type=rel_type, **(record.get("rel_props") or {}))
                
        return G

    def calculate_centrality(self, G: nx.DiGraph) -> Dict[str, Dict[str, float]]:
        """Calculates PageRank and Betweenness Centrality."""
        logger.info(f"Calculating centrality metrics for {G.number_of_nodes()} nodes...")
        try:
            pagerank = nx.pagerank(G, weight='weight', max_iter=100)
        except nx.PowerIterationFailedConvergence:
            logger.warning("PageRank failed to converge. Falling back to default.")
            pagerank = {n: 0.0 for n in G.nodes()}
            
        betweenness = nx.betweenness_centrality(G, weight='weight')
        closeness = nx.closeness_centrality(G)
        
        metrics = {}
        for node in G.nodes():
            metrics[node] = {
                "pagerank": pagerank.get(node, 0.0),
                "betweenness": betweenness.get(node, 0.0),
                "closeness": closeness.get(node, 0.0)
            }
        return metrics

    def calculate_communities(self, G: nx.DiGraph) -> Dict[str, int]:
        """Calculates Louvain communities (on undirected version of the graph)."""
        logger.info("Calculating Louvain communities...")
        undirected_G = G.to_undirected()
        try:
            partition = community_louvain.best_partition(undirected_G, weight='weight')
            return partition
        except Exception as e:
            logger.error(f"Failed to calculate communities: {e}")
            return {n: 0 for n in G.nodes()}

    def calculate_shortest_path(self, source_id: str, target_id: str) -> Optional[List[str]]:
        """Calculates shortest path using Dijkstra."""
        G = self.fetch_full_graph()
        # Find internal node ID matching the string ID
        src_internal = None
        tgt_internal = None
        
        for node, data in G.nodes(data=True):
            if data.get('id') == source_id:
                src_internal = node
            if data.get('id') == target_id:
                tgt_internal = node
                
        if not src_internal or not tgt_internal:
            logger.warning("Source or target node not found in graph by 'id' property.")
            return None
            
        try:
            path = nx.shortest_path(G, source=src_internal, target=tgt_internal)
            # Map back to string IDs
            mapped_path = []
            for n in path:
                mapped_path.append(G.nodes[n].get('id', n))
            return mapped_path
        except nx.NetworkXNoPath:
            return None

    def run_full_analytics(self) -> Dict[str, Any]:
        """Runs all analytics and persists to Neo4j."""
        G = self.fetch_full_graph()
        if G.number_of_nodes() == 0:
            return {"status": "skipped", "message": "Graph is empty"}
            
        centrality = self.calculate_centrality(G)
        communities = self.calculate_communities(G)
        
        # Combine metrics
        updates = []
        for node in G.nodes():
            element_id = node
            metrics = centrality.get(node, {})
            metrics["community_id"] = communities.get(node, -1)
            updates.append({
                "element_id": element_id,
                "metrics": metrics
            })
            
        # Persist to Neo4j
        self.persist_metrics(updates)
        
        return {
            "status": "success",
            "nodes_analyzed": G.number_of_nodes(),
            "edges_analyzed": G.number_of_edges()
        }
        
    def persist_metrics(self, updates: List[Dict[str, Any]]):
        """Batch updates Neo4j nodes with calculated metrics using elementId."""
        query = """
        UNWIND $updates AS update
        MATCH (n) WHERE elementId(n) = update.element_id
        SET n.pagerank = update.metrics.pagerank,
            n.betweenness = update.metrics.betweenness,
            n.closeness = update.metrics.closeness,
            n.community_id = update.metrics.community_id
        """
        # Process in batches to avoid OOM
        batch_size = 500
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            self.neo4j.run_query(query, parameters={"updates": batch})
            logger.info(f"Persisted metrics for {len(batch)} nodes.")

graph_analytics = GraphAnalyticsService()
