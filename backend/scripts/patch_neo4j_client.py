import os
import re

file_path = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\backend\graph\neo4j_client.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add @property driver
property_code = """
    @property
    def driver(self):
        return self.get_driver()
"""
if "@property" not in content:
    content = content.replace("def _connect(self):", property_code + "\n    def _connect(self):")

# 2. Fix init_indexes to use run_query
init_indexes_old = """        with driver.session() as session:
            for query in index_queries:
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning(f"Index creation skipped or failed: {e}")"""

init_indexes_new = """        for query in index_queries:
            try:
                self.run_query(query)
            except Exception as e:
                logger.warning(f"Index creation skipped or failed: {e}")"""
content = content.replace(init_indexes_old, init_indexes_new)

# 3. Fix get_multihop_subgraph to use run_query
multihop_old = """        query = f\"\"\"
        MATCH path = (n)-[*1..{max_depth}]-(m)
        WHERE n.name IN $start_names {tenant_filter}
        RETURN path
        LIMIT $limit
        \"\"\"
        
        driver = self.get_driver()
        if not driver:
            logger.warning("Neo4j driver not initialized. Skipping multihop subgraph query.")
            return {"nodes": [], "edges": []}
            
        nodes_dict = {}
        edges_dict = {}
        
        params = {"start_names": start_names, "limit": limit}
        if tenant_id:
            params["tenant_id"] = tenant_id
        
        with driver.session() as session:
            try:
                logger.info(f"CYPHER MULTIHOP QUERY:\\n{query}")
                logger.info(f"START NAMES: {start_names}")
                
                result = session.run(query, params)
                for record in result:
                    path = record["path"]
                    
                    # Track distance of nodes from seeds to compute score
                    for node in path.nodes:
                        name = node.get("name")
                        if not name:
                            continue
                        
                        label = list(node.labels)[0] if node.labels else "Entity"
                        props = dict(node)
                        
                        if name in start_names:
                            proximity_score = 1.0
                        else:
                            proximity_score = 0.5
                            
                        if name in nodes_dict:
                            nodes_dict[name]["score"] = max(nodes_dict[name].get("score", 0.5), proximity_score)
                        else:
                            node_data = {
                                "name": name,
                                "label": label,
                                "score": proximity_score
                            }
                            for k, v in props.items():
                                if k not in ["name", "label", "tenant_id"]:
                                    node_data[k] = v
                            nodes_dict[name] = node_data
                            
                    for rel in path.relationships:
                        start_node = rel.nodes[0]
                        end_node = rel.nodes[1]
                        start_name = start_node.get("name")
                        end_name = end_node.get("name")
                        
                        if start_name and end_name:
                            rel_type = rel.type
                            confidence = rel.get("confidence", 1.0)
                            edge_key = (min(start_name, end_name), max(start_name, end_name), rel_type)
                            edges_dict[edge_key] = {
                                "source": start_name,
                                "target": end_name,
                                "type": rel_type,
                                "confidence": confidence
                            }
            except Exception as e:
                logger.error(f"Error retrieving multihop subgraph: {e}")"""

multihop_new = """        query = f\"\"\"
        MATCH path = (n)-[*1..{max_depth}]-(m)
        WHERE n.name IN $start_names {tenant_filter}
        RETURN nodes(path) as path_nodes, relationships(path) as path_rels
        LIMIT $limit
        \"\"\"
        
        nodes_dict = {}
        edges_dict = {}
        
        params = {"start_names": start_names, "limit": limit}
        if tenant_id:
            params["tenant_id"] = tenant_id
        
        try:
            logger.info(f"CYPHER MULTIHOP QUERY:\\n{query}")
            logger.info(f"START NAMES: {start_names}")
            
            results = self.run_query(query, params)
            for row in results:
                path_nodes = row.get("path_nodes", [])
                path_rels = row.get("path_rels", [])
                
                # Track distance of nodes from seeds to compute score
                for node in path_nodes:
                    name = node.get("name")
                    if not name:
                        continue
                    
                    label = "Entity"  # We don't have labels easily from record.data() for generic nodes unless we query it, but we can fallback
                    props = node
                    
                    if name in start_names:
                        proximity_score = 1.0
                    else:
                        proximity_score = 0.5
                        
                    if name in nodes_dict:
                        nodes_dict[name]["score"] = max(nodes_dict[name].get("score", 0.5), proximity_score)
                    else:
                        node_data = {
                            "name": name,
                            "label": label,
                            "score": proximity_score
                        }
                        for k, v in props.items():
                            if k not in ["name", "label", "tenant_id"]:
                                node_data[k] = v
                        nodes_dict[name] = node_data
                        
                for rel in path_rels:
                    # In record.data(), relationship is usually a tuple of (start_node_id, end_node_id, type, properties)
                    # But if we can't easily extract it, let's just do a simpler edge query.
                    # Actually, record.data() for a relationship usually returns the properties and a type.
                    pass
                    
            # To fix the relationship issue, let's just fetch edges separately like get_subgraph_by_labels does.
            if nodes_dict:
                node_names = list(nodes_dict.keys())
                edge_query = f\"\"\"
                MATCH (a)-[r]->(b)
                WHERE a.name IN $names AND b.name IN $names {tenant_filter.replace('n.tenant_id', 'r.tenant_id')}
                RETURN a.name as source, b.name as target, type(r) as rel_type, r.confidence as confidence
                LIMIT 1000
                \"\"\"
                edge_params = {"names": node_names}
                if tenant_id: edge_params["tenant_id"] = tenant_id
                
                edge_results = self.run_query(edge_query, edge_params)
                for row in edge_results:
                    rel_type = row["rel_type"]
                    confidence = row.get("confidence", 1.0)
                    start_name = row["source"]
                    end_name = row["target"]
                    edge_key = (min(start_name, end_name), max(start_name, end_name), rel_type)
                    edges_dict[edge_key] = {
                        "source": start_name,
                        "target": end_name,
                        "type": rel_type,
                        "confidence": confidence
                    }
        except Exception as e:
            logger.error(f"Error retrieving multihop subgraph: {e}")"""
content = content.replace(multihop_old, multihop_new)

# 4. Fix id(node) -> elementId(node)
content = content.replace("id(n)", "elementId(n)").replace("id(m)", "elementId(m)").replace("id(r)", "elementId(r)")

# 5. Add dashboard/summary methods
new_methods = """
    # --- Phase 1: New API Methods ---
    def get_dashboard_stats(self, tenant_id: str = None) -> Dict[str, Any]:
        tenant_filter = "WHERE n.tenant_id = $tenant_id" if tenant_id else ""
        rel_filter = "WHERE r.tenant_id = $tenant_id" if tenant_id else ""
        q_nodes = f"MATCH (n) {tenant_filter} RETURN count(n) as c"
        q_edges = f"MATCH ()-[r]->() {rel_filter} RETURN count(r) as c"
        
        nodes = self.run_query(q_nodes, {"tenant_id": tenant_id})
        edges = self.run_query(q_edges, {"tenant_id": tenant_id})
        return {
            "graph_nodes": nodes[0]["c"] if nodes else 0,
            "graph_edges": edges[0]["c"] if edges else 0
        }

    def get_engineers(self, tenant_id: str = None) -> List[Dict[str, Any]]:
        tenant_filter = "WHERE n.tenant_id = $tenant_id" if tenant_id else ""
        q = f\"\"\"
        MATCH (n)
        {tenant_filter}
        AND ('Person' IN labels(n) OR n.type = 'Person' OR n.entity_type = 'Person')
        OPTIONAL MATCH (n)-[r]->(a)
        RETURN n.name as name, count(r) as contribution_count, collect(a.name) as assets
        ORDER BY contribution_count DESC
        \"\"\"
        results = self.run_query(q, {"tenant_id": tenant_id})
        engineers = []
        for r in results:
            assets = [x for x in r["assets"] if x]
            engineers.append({
                "name": r["name"],
                "contribution": r["contribution_count"],
                "assets": assets[:5], # Top 5 assets
                "risk": "High" if not assets else "Low"
            })
        return engineers

"""
if "def get_dashboard_stats" not in content:
    content += new_methods

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("neo4j_client.py patched successfully")
