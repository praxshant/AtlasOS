import logging
import time
import json
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class Neo4jClient:
    def __init__(self):
        self.uri = settings.NEO4J_URI
        self.user = settings.NEO4J_USER
        self.password = settings.NEO4J_PASSWORD
        self._driver = None
        self._connect()

    def _connect(self):
        try:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # Verify connectivity
            self._driver.verify_connectivity()
            logger.info("Successfully connected to Neo4j database.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j at {self.uri}: {e}")
            self._driver = None

    def close(self):
        if self._driver:
            self._driver.close()
            logger.info("Closed Neo4j driver connection.")

    def get_driver(self):
        if not self._driver:
            self._connect()
        return self._driver

    def init_indexes(self):
        """
        Creates indexes and constraints for optimal query performance.
        Called at application startup.
        """
        driver = self.get_driver()
        if not driver:
            logger.warning("Neo4j driver not initialized. Skipping index creation.")
            return

        index_queries = [
            # Property indexes
            "CREATE INDEX tenant_idx IF NOT EXISTS FOR (n:Entity) ON (n.tenant_id)",
            "CREATE INDEX name_idx IF NOT EXISTS FOR (n:Entity) ON (n.name)",
            "CREATE INDEX source_doc_idx IF NOT EXISTS FOR (n:Entity) ON (n.source_doc_id)",
            # Per-label tenant indexes
            "CREATE INDEX asset_tenant IF NOT EXISTS FOR (n:Asset) ON (n.tenant_id)",
            "CREATE INDEX person_tenant IF NOT EXISTS FOR (n:Person) ON (n.tenant_id)",
            "CREATE INDEX incident_tenant IF NOT EXISTS FOR (n:Incident) ON (n.tenant_id)",
            "CREATE INDEX procedure_tenant IF NOT EXISTS FOR (n:Procedure) ON (n.tenant_id)",
            "CREATE INDEX regulation_tenant IF NOT EXISTS FOR (n:Regulation) ON (n.tenant_id)",
            "CREATE INDEX failuremode_tenant IF NOT EXISTS FOR (n:FailureMode) ON (n.tenant_id)",
            "CREATE INDEX equipment_tenant IF NOT EXISTS FOR (n:Equipment) ON (n.tenant_id)",
            "CREATE INDEX lessonlearned_tenant IF NOT EXISTS FOR (n:LessonLearned) ON (n.tenant_id)",
            "CREATE INDEX auditfinding_tenant IF NOT EXISTS FOR (n:AuditFinding) ON (n.tenant_id)",
            # Name indexes per label
            "CREATE INDEX asset_name IF NOT EXISTS FOR (n:Asset) ON (n.name)",
            "CREATE INDEX person_name IF NOT EXISTS FOR (n:Person) ON (n.name)",
            "CREATE INDEX incident_name IF NOT EXISTS FOR (n:Incident) ON (n.name)",
        ]

        with driver.session() as session:
            for query in index_queries:
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning(f"Index creation skipped or failed: {e}")

        logger.info("Neo4j indexes initialized.")

    def run_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Executes a Cypher query and returns the results as a list of dictionaries with backoff retries.
        """
        driver = self.get_driver()
        if not driver:
            logger.warning("Neo4j driver not initialized. Skipping query.")
            return []
            
        max_retries = 3
        backoff = 0.5
        
        from backend.utils.circuit_breaker import neo4j_breaker, CircuitOpenError
        
        def _do_query():
            with driver.session() as session:
                result = session.run(query, parameters or {})
                return [record.data() for record in result]
        
        for attempt in range(max_retries):
            try:
                return neo4j_breaker.call(_do_query)
            except CircuitOpenError as ce:
                logger.warning(f"Neo4j circuit is OPEN. Skipping query: {ce}")
                return []
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Cypher query error after {max_retries} attempts: {e}\nQuery: {query}")
                    raise e
                logger.warning(f"Neo4j query attempt {attempt + 1} failed: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
        return []

    def find_node(self, label: str, name: str, tenant_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Finds a single node by label and name, scoped to tenant.
        """
        tenant_filter = "AND n.tenant_id = $tenant_id" if tenant_id else ""
        query = f"MATCH (n:{label} {{name: $name}}) WHERE true {tenant_filter} RETURN n"
        params = {"name": name}
        if tenant_id:
            params["tenant_id"] = tenant_id
        results = self.run_query(query, params)
        if results:
            return results[0]["n"]
        return None

    def get_neighbors(self, name: str, tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Gets immediate neighbors (nodes and relationship types) of a node by its name, scoped to tenant.
        """
        tenant_filter = "AND n.tenant_id = $tenant_id AND m.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (n {{name: $name}})-[r]-(m)
        WHERE true {tenant_filter}
        RETURN labels(m) as labels, m as properties, m.name as name, type(r) as relationship, 
               r.confidence as confidence, r.source_doc_id as source_doc_id
        LIMIT 50
        """
        params = {"name": name}
        if tenant_id:
            params["tenant_id"] = tenant_id
        return self.run_query(query, params)

    def get_shortest_path(self, start_name: str, end_name: str, max_depth: int = 5, tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Finds the shortest path between two nodes by their names, scoped to tenant.
        """
        tenant_filter = "AND start.tenant_id = $tenant_id AND end.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (start {{name: $start_name}}), (end {{name: $end_name}})
        WHERE true {tenant_filter}
        MATCH p = shortestPath((start)-[*..{max_depth}]-(end))
        RETURN p
        """
        params = {"start_name": start_name, "end_name": end_name}
        if tenant_id:
            params["tenant_id"] = tenant_id
        results = self.run_query(query, params)
        if results:
            return results[0]["p"]
        return []

    def fulltext_search(self, search_term: str, tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Fuzzy search for nodes containing a name or description matching the search term, scoped to tenant.
        """
        tenant_filter = "AND n.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (n)
        WHERE ((n.name IS NOT NULL AND (toLower($term) CONTAINS toLower(n.name) OR toLower(n.name) CONTAINS toLower($term)))
           OR (n.description IS NOT NULL AND (toLower($term) CONTAINS toLower(n.description) OR toLower(n.description) CONTAINS toLower($term))))
           {tenant_filter}
        RETURN labels(n) as labels, n as properties, n.name as name, n.description as description, 
               n.source_doc_id as source_doc_id, n.confidence as confidence
        LIMIT 20
        """
        logger.info(f"CYPHER:\n{query}")
        logger.info(f"QUERY PARAM: {search_term}")
        params = {"term": search_term}
        if tenant_id:
            params["tenant_id"] = tenant_id
        return self.run_query(query, params)

    def get_multihop_subgraph(self, start_names: List[str], max_depth: int = 3, limit: int = 100, tenant_id: str = None) -> Dict[str, Any]:
        """
        Retrieves a subgraph of paths up to max_depth hops starting from start_names, scoped to tenant.
        Returns a dict with "nodes" and "edges" list, with calculated scores.
        """
        if not start_names:
            return {"nodes": [], "edges": []}

        tenant_filter = "AND n.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH path = (n)-[*1..{max_depth}]-(m)
        WHERE n.name IN $start_names {tenant_filter}
        RETURN path
        LIMIT $limit
        """
        
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
                logger.info(f"CYPHER MULTIHOP QUERY:\n{query}")
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
                logger.error(f"Error retrieving multihop subgraph: {e}")
                
        return {
            "nodes": list(nodes_dict.values()),
            "edges": list(edges_dict.values())
        }

    # --- Phase 2: Graph Explorer API Methods ---

    def get_neighborhood(self, node_name: str, depth: int = 2, limit: int = 100, tenant_id: str = None) -> Dict[str, Any]:
        """
        Returns the N-hop neighborhood around a specific node.
        Used by the Graph Explorer for click-to-expand.
        """
        return self.get_multihop_subgraph([node_name], max_depth=depth, limit=limit, tenant_id=tenant_id)

    def get_subgraph_by_labels(self, labels: List[str], limit: int = 500, tenant_id: str = None) -> Dict[str, Any]:
        """
        Returns nodes and edges filtered by specific labels.
        Used by the Graph Explorer for label filtering.
        """
        if not labels:
            return {"nodes": [], "edges": []}

        label_clause = " OR ".join([f"'{l}' IN labels(n)" for l in labels])
        tenant_filter = "AND n.tenant_id = $tenant_id" if tenant_id else ""
        
        # Fetch nodes
        node_query = f"""
        MATCH (n)
        WHERE ({label_clause}) {tenant_filter}
        RETURN labels(n) as labels, n as properties, n.name as name
        LIMIT $limit
        """
        params = {"limit": limit}
        if tenant_id:
            params["tenant_id"] = tenant_id
            
        nodes_dict = {}
        try:
            node_results = self.run_query(node_query, params)
            for row in node_results:
                name = row.get("name")
                if name:
                    label = row["labels"][0] if row["labels"] else "Entity"
                    props = row.get("properties", {})
                    node_data = {"name": name, "label": label}
                    for k, v in props.items():
                        if k not in ["name", "tenant_id"]:
                            node_data[k] = v
                    nodes_dict[name] = node_data
        except Exception as e:
            logger.error(f"Error fetching subgraph by labels: {e}")
            return {"nodes": [], "edges": []}

        # Fetch edges between those nodes
        if not nodes_dict:
            return {"nodes": [], "edges": []}
            
        node_names = list(nodes_dict.keys())
        edge_tenant_filter = "AND r.tenant_id = $tenant_id" if tenant_id else ""
        edge_query = f"""
        MATCH (a)-[r]->(b)
        WHERE a.name IN $names AND b.name IN $names {edge_tenant_filter}
        RETURN a.name as source, b.name as target, type(r) as rel_type, r.confidence as confidence
        LIMIT 1000
        """
        edge_params = {"names": node_names}
        if tenant_id:
            edge_params["tenant_id"] = tenant_id

        edges = []
        try:
            edge_results = self.run_query(edge_query, edge_params)
            for row in edge_results:
                edges.append({
                    "source": row["source"],
                    "target": row["target"],
                    "type": row["rel_type"],
                    "confidence": row.get("confidence", 1.0)
                })
        except Exception as e:
            logger.error(f"Error fetching edges for subgraph: {e}")

        return {
            "nodes": list(nodes_dict.values()),
            "edges": edges
        }

    def get_label_stats(self, tenant_id: str = None) -> Dict[str, int]:
        """
        Returns node counts grouped by label.
        Used by the Graph Explorer for label distribution display.
        """
        tenant_filter = "WHERE n.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (n)
        {tenant_filter}
        UNWIND labels(n) AS label
        RETURN label, count(*) as count
        ORDER BY count DESC
        """
        params = {}
        if tenant_id:
            params["tenant_id"] = tenant_id
            
        try:
            results = self.run_query(query, params)
            return {row["label"]: row["count"] for row in results}
        except Exception as e:
            logger.error(f"Error fetching label stats: {e}")
            return {}

    def search_nodes(self, search_term: str, limit: int = 20, tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Quick node search by name for Graph Explorer autocomplete.
        """
        tenant_filter = "AND n.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (n)
        WHERE n.name IS NOT NULL AND toLower(n.name) CONTAINS toLower($term) {tenant_filter}
        RETURN labels(n) as labels, n.name as name, n.description as description
        LIMIT $limit
        """
        params = {"term": search_term, "limit": limit}
        if tenant_id:
            params["tenant_id"] = tenant_id
        try:
            return self.run_query(query, params)
        except Exception as e:
            logger.error(f"Error searching nodes: {e}")
            return []

    # -------------------------------------------------------------------
    # Phase X — Knowledge Gap Detector
    # -------------------------------------------------------------------

    # Expected document categories for any equipment / asset entity.
    # These correspond to relationship types or connected node labels
    # that should be present for a fully documented asset.
    EXPECTED_KNOWLEDGE_CATEGORIES: List[str] = [
        "SOP",          # Standard Operating Procedure
        "Inspection",   # Inspection record
        "Maintenance",  # Maintenance event
        "Failure",      # Failure history / incident
        "Compliance",   # Regulatory / compliance record
    ]

    # Map from graph relationship types / node labels to knowledge categories
    _CATEGORY_SIGNALS: Dict[str, str] = {
        # Relationship types
        "MAINTAINED_BY": "Maintenance",
        "INSPECTED_BY": "Inspection",
        "RESULTED_IN": "Failure",
        "CAUSED_BY": "Failure",
        "COMPLIES_WITH": "Compliance",
        "VIOLATES": "Compliance",
        "APPLIES_TO": "SOP",
        "PREVENTS": "SOP",
        # Node labels
        "Procedure": "SOP",
        "Incident": "Failure",
        "FailureMode": "Failure",
        "Regulation": "Compliance",
        "AuditFinding": "Compliance",
        "LessonLearned": "SOP",
    }

    def compute_knowledge_coverage_score(self, equipment_name: str, tenant_id: str = None) -> Dict[str, Any]:
        """Advanced weighted coverage scoring for one asset."""
        tid = tenant_id or "default"
        
        q1 = "MATCH (a {name: $name, tenant_id: $tid})-[:PREVENTS|COMPLIES_WITH]-(p:Procedure) RETURN count(p) > 0 AS has_sop"
        q2 = "MATCH (a {name: $name, tenant_id: $tid})<-[:OCCURRED_ON]-(i:Incident) RETURN count(i) AS incident_count"
        q3 = "MATCH (a {name: $name, tenant_id: $tid})<-[:PERFORMED_ON|MAINTAINED_BY]-(m) RETURN count(m) AS maintenance_count"
        q4 = "MATCH (a {name: $name, tenant_id: $tid})-[:COMPLIES_WITH]->(r:Regulation) RETURN count(r) > 0 AS has_compliance"
        q5 = "MATCH (a {name: $name, tenant_id: $tid})<-[:KNOWLEDGE_OWNER_FOR|MAINTAINED_BY]-(p:Person) RETURN count(p) > 0 AS has_expert, collect(p.name) AS experts"
        
        params = {"name": equipment_name, "tid": tid}
        
        res1 = self.run_query(q1, params)
        has_sop = res1[0]["has_sop"] if res1 else False
        
        res2 = self.run_query(q2, params)
        has_incident_history = (res2[0]["incident_count"] > 0) if res2 else False
        
        res3 = self.run_query(q3, params)
        has_maintenance = (res3[0]["maintenance_count"] > 0) if res3 else False
        
        res4 = self.run_query(q4, params)
        has_compliance = res4[0]["has_compliance"] if res4 else False
        
        res5 = self.run_query(q5, params)
        has_expert = res5[0]["has_expert"] if res5 else False
        experts = res5[0]["experts"] if res5 else []
        
        score = int((
            0.25 * int(has_sop) +
            0.20 * int(has_incident_history) +
            0.20 * int(has_maintenance) +
            0.20 * int(has_compliance) +
            0.15 * int(has_expert)
        ) * 100)
        
        missing = [cat for cat, present in zip(
            ["SOP", "Incident History", "Maintenance", "Compliance", "Expert Owner"],
            [has_sop, has_incident_history, has_maintenance, has_compliance, has_expert]
        ) if not present]
        
        return {
            "equipment": equipment_name,
            "coverage_score": score,
            "has_sop": has_sop,
            "has_incident_history": has_incident_history,
            "has_maintenance": has_maintenance,
            "has_compliance": has_compliance,
            "has_expert": has_expert,
            "experts": experts,
            "missing_categories": missing
        }

    def compute_risk_score(self, equipment_name: str, tenant_id: str = None) -> Dict[str, Any]:
        """Multi-factor explainable risk scoring for one asset."""
        tid = tenant_id or "default"
        risk_factors = []
        risk_score = 0
        
        # Factor 1
        q1 = """
        MATCH (a {name: $name, tenant_id: $tid})<-[:OCCURRED_ON]-(i:Incident)
        WHERE toLower(i.name) CONTAINS 'catastrophic' OR toLower(i.name) CONTAINS 'emergency' OR toLower(i.name) CONTAINS 'critical'
        RETURN count(i) AS severe_incidents
        """
        res1 = self.run_query(q1, {"name": equipment_name, "tid": tid})
        severe_incidents = res1[0]["severe_incidents"] if res1 else 0
        if severe_incidents > 0:
            risk_score += 30
            risk_factors.append("Has documented catastrophic or emergency incident")
            
        # Factor 2
        coverage = self.compute_knowledge_coverage_score(equipment_name, tenant_id)
        if coverage["coverage_score"] < 50:
            risk_score += 25
            risk_factors.append(f"Knowledge coverage is low ({coverage['coverage_score']}%)")
        elif coverage["coverage_score"] < 75:
            risk_score += 10
            
        # Factor 3
        q3 = """
        MATCH (a {name: $name, tenant_id: $tid})<-[:KNOWLEDGE_OWNER_FOR|MAINTAINED_BY]-(p:Person)
        RETURN count(p) AS expert_count
        """
        res3 = self.run_query(q3, {"name": equipment_name, "tid": tid})
        expert_count = res3[0]["expert_count"] if res3 else 0
        if expert_count == 1:
            risk_score += 20
            risk_factors.append("Only one engineer holds knowledge of this asset")
        elif expert_count == 0:
            risk_score += 20
            risk_factors.append("No engineer is linked as knowledge owner")
            
        # Factor 4
        q4 = """
        MATCH (a {name: $name, tenant_id: $tid})-[:FEEDS|SUPPLIES|CONNECTED_TO]-(b)
        WHERE exists((b)<-[:OCCURRED_ON]-(:Incident))
        RETURN count(b) AS critical_neighbors
        """
        res4 = self.run_query(q4, {"name": equipment_name, "tid": tid})
        critical_neighbors = res4[0]["critical_neighbors"] if res4 else 0
        if critical_neighbors > 0:
            risk_score += 15
            risk_factors.append(f"Connected to {critical_neighbors} asset(s) with incident history")
            
        # Factor 5
        if coverage["has_incident_history"] and not coverage["has_sop"]:
            risk_score += 10
            risk_factors.append("Has incident history but no Standard Operating Procedure")
            
        risk_score = min(risk_score, 100)
        risk_level = "Critical" if risk_score >= 70 else "High" if risk_score >= 40 else "Medium" if risk_score >= 20 else "Low"
        
        return {
            "equipment": equipment_name,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "coverage": coverage
        }

    def compute_knowledge_gaps(
        self,
        equipment_name: str,
        tenant_id: str = None
    ) -> Dict[str, Any]:
        """
        Computes the knowledge coverage score for a given equipment / asset node.

        Algorithm:
        1. Fetch all immediate relationships and connected node labels for the node.
        2. Map each relationship type / neighbour label to one of the five
           EXPECTED_KNOWLEDGE_CATEGORIES.
        3. discovered  = set of categories that have at least one signal.
        4. missing     = EXPECTED_KNOWLEDGE_CATEGORIES - discovered.
        5. coverage %  = len(discovered) / len(EXPECTED) * 100
        6. Upsert a HAS_KNOWLEDGE_GAP relationship from the asset to each
           MissingCategory node so the gap is visible in the graph explorer.

        Returns:
            {
              "equipment": str,
              "coverage_pct": float,
              "discovered": [str],
              "missing": [str]
            }
        """
        tenant_filter = "AND n.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (n {{name: $name}})-[r]-(m)
        WHERE true {tenant_filter}
        RETURN type(r) as rel_type, labels(m) as m_labels
        LIMIT 200
        """
        params: Dict[str, Any] = {"name": equipment_name}
        if tenant_id:
            params["tenant_id"] = tenant_id

        try:
            rows = self.run_query(query, params)
        except Exception as e:
            logger.error(f"Knowledge gap query failed for {equipment_name}: {e}")
            return {
                "equipment": equipment_name,
                "coverage_pct": 0.0,
                "discovered": [],
                "missing": list(self.EXPECTED_KNOWLEDGE_CATEGORIES)
            }

        discovered: set = set()
        for row in rows:
            rel = row.get("rel_type", "")
            if rel in self._CATEGORY_SIGNALS:
                discovered.add(self._CATEGORY_SIGNALS[rel])
            for lbl in (row.get("m_labels") or []):
                if lbl in self._CATEGORY_SIGNALS:
                    discovered.add(self._CATEGORY_SIGNALS[lbl])

        expected_set = set(self.EXPECTED_KNOWLEDGE_CATEGORIES)
        missing = sorted(expected_set - discovered)
        coverage_pct = round(len(discovered) / len(expected_set) * 100, 1)

        # Persist gap nodes + relationships so the graph explorer can render them
        if missing:
            _tid = tenant_id or "default"
            for cat in missing:
                gap_cypher = """
                MERGE (gap:MissingCategory {name: $cat, tenant_id: $tenant_id})
                WITH gap
                MATCH (eq {name: $eq_name, tenant_id: $tenant_id})
                MERGE (eq)-[g:HAS_KNOWLEDGE_GAP]->(gap)
                ON CREATE SET g.tenant_id = $tenant_id, g.created_at = timestamp()
                """
                try:
                    self.run_query(gap_cypher, {
                        "cat": cat,
                        "tenant_id": _tid,
                        "eq_name": equipment_name
                    })
                except Exception as e:
                    logger.warning(f"Could not persist gap node for {equipment_name}/{cat}: {e}")

        return {
            "equipment": equipment_name,
            "coverage_pct": coverage_pct,
            "discovered": sorted(discovered),
            "missing": missing
        }

    def get_all_equipment_gaps(
        self,
        tenant_id: str = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Returns knowledge gap reports for ALL equipment / asset nodes
        in the tenant's graph, augmented with risk scores.
        """
        tenant_filter = "WHERE n.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (n)
        WHERE (n:Asset OR n:Equipment) {('AND n.tenant_id = $tenant_id') if tenant_id else ''}
        RETURN DISTINCT n.name as name
        LIMIT $limit
        """
        params: Dict[str, Any] = {"limit": limit}
        if tenant_id:
            params["tenant_id"] = tenant_id

        try:
            rows = self.run_query(query, params)
        except Exception as e:
            logger.error(f"Failed to list equipment for gap analysis: {e}")
            return []

        results = []
        for row in rows:
            name = row.get("name")
            if name:
                asset_dict = {"equipment": name}
                
                # Fetch basic gaps using existing logic if needed, but we will overwrite with advanced coverage
                gap = self.compute_knowledge_gaps(name, tenant_id=tenant_id)
                asset_dict["discovered"] = gap["discovered"]
                asset_dict["missing"] = gap["missing"]
                
                coverage_data = self.compute_knowledge_coverage_score(name, tenant_id)
                asset_dict["coverage_score"] = coverage_data["coverage_score"]
                asset_dict["missing_categories"] = coverage_data["missing_categories"]
                
                risk_data = self.compute_risk_score(name, tenant_id)
                asset_dict["risk_score"] = risk_data["risk_score"]
                asset_dict["risk_level"] = risk_data["risk_level"]
                
                results.append(asset_dict)

        results.sort(key=lambda x: x["risk_score"], reverse=True)
        return results

    # -------------------------------------------------------------------
    # Phase X — Engineer Knowledge Preservation Engine
    # -------------------------------------------------------------------

    def get_engineer_expertise(
        self,
        engineer_name: str,
        tenant_id: str = None
    ) -> Dict[str, Any]:
        """
        Derives an engineer's expertise from their existing graph relationships.

        Counts:
        - Assets they MAINTAINED_BY, INSPECTED_BY
        - Incidents they REPORTED_BY / INVESTIGATED
        - Documents they authored (AUTHORED relationship)
        - Regulations / procedures they are linked to

        Returns per-equipment-category contribution scores and an
        aggregate expertise_score (0-100).
        """
        tenant_filter = "AND p.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (p {{name: $name}})-[r]-(asset)
        WHERE true {tenant_filter}
        RETURN type(r) as rel_type, labels(asset) as asset_labels, asset.name as asset_name
        LIMIT 500
        """
        params: Dict[str, Any] = {"name": engineer_name}
        if tenant_id:
            params["tenant_id"] = tenant_id

        try:
            rows = self.run_query(query, params)
        except Exception as e:
            logger.error(f"Engineer expertise query failed for {engineer_name}: {e}")
            return {
                "engineer": engineer_name,
                "expertise_score": 0,
                "total_events": 0,
                "breakdown": {},
                "equipment_touched": []
            }

        # Tally events
        maintenance_count = 0
        inspection_count = 0
        incident_count = 0
        authored_count = 0
        equipment_touched: set = set()

        for row in rows:
            rel = row.get("rel_type", "")
            labels = row.get("asset_labels") or []
            asset = row.get("asset_name", "")

            if rel in ("MAINTAINED_BY", "MAINTAINED"):
                maintenance_count += 1
                if asset:
                    equipment_touched.add(asset)
            elif rel in ("INSPECTED_BY", "INSPECTED"):
                inspection_count += 1
                if asset:
                    equipment_touched.add(asset)
            elif rel in ("REPORTED_BY", "INVESTIGATED", "RESULTED_IN"):
                incident_count += 1
            elif rel in ("AUTHORED", "AUTHORED_BY"):
                authored_count += 1

            # Asset / Equipment labels also count
            if "Asset" in labels or "Equipment" in labels:
                if asset:
                    equipment_touched.add(asset)

        total_events = maintenance_count + inspection_count + incident_count + authored_count
        # Weighted expertise score (max 100)
        raw_score = (
            maintenance_count * 3
            + inspection_count * 2
            + incident_count * 4
            + authored_count * 1
        )
        expertise_score = min(round(raw_score), 100)

        return {
            "engineer": engineer_name,
            "expertise_score": expertise_score,
            "total_events": total_events,
            "breakdown": {
                "maintenance_events": maintenance_count,
                "inspections": inspection_count,
                "incidents_investigated": incident_count,
                "documents_authored": authored_count,
            },
            "equipment_touched": sorted(equipment_touched)
        }

    def get_knowledge_risk_by_equipment(
        self,
        equipment_name: str,
        tenant_id: str = None
    ) -> Dict[str, Any]:
        """
        For a given piece of equipment, determines which engineers
        hold majority knowledge and assesses retirement risk.

        Returns:
            {
              "equipment": str,
              "risk_level": "HIGH" | "MEDIUM" | "LOW",
              "top_engineers": [{"name": str, "contribution_pct": float}],
              "rationale": str
            }
        """
        tenant_filter = "AND asset.tenant_id = $tenant_id" if tenant_id else ""
        query = f"""
        MATCH (person:Person)-[r]-(asset {{name: $eq_name}})
        WHERE true {tenant_filter}
        RETURN person.name as engineer, count(r) as event_count
        ORDER BY event_count DESC
        LIMIT 20
        """
        params: Dict[str, Any] = {"eq_name": equipment_name}
        if tenant_id:
            params["tenant_id"] = tenant_id

        try:
            rows = self.run_query(query, params)
        except Exception as e:
            logger.error(f"Knowledge risk query failed for {equipment_name}: {e}")
            return {
                "equipment": equipment_name,
                "risk_level": "UNKNOWN",
                "top_engineers": [],
                "rationale": f"Query failed: {e}"
            }

        if not rows:
            return {
                "equipment": equipment_name,
                "risk_level": "LOW",
                "top_engineers": [],
                "rationale": "No engineer-equipment relationships found in graph."
            }

        total_events = sum(r["event_count"] for r in rows)
        engineers_pct = []
        for row in rows:
            pct = round(row["event_count"] / total_events * 100, 1) if total_events else 0.0
            engineers_pct.append({"name": row["engineer"], "contribution_pct": pct})

        # Risk logic: if top engineer owns >60% of events → HIGH
        top_pct = engineers_pct[0]["contribution_pct"] if engineers_pct else 0
        if top_pct >= 60:
            risk_level = "HIGH"
            rationale = (
                f"{engineers_pct[0]['name']} holds {top_pct}% of documented knowledge "
                f"for {equipment_name}. Retirement would create a critical knowledge gap."
            )
        elif top_pct >= 40:
            risk_level = "MEDIUM"
            rationale = (
                f"{engineers_pct[0]['name']} holds {top_pct}% of documented knowledge "
                f"for {equipment_name}. Moderate concentration risk."
            )
        else:
            risk_level = "LOW"
            rationale = (
                f"Knowledge for {equipment_name} is distributed across multiple engineers. "
                "Retirement risk is low."
            )

        return {
            "equipment": equipment_name,
            "risk_level": risk_level,
            "top_engineers": engineers_pct,
            "rationale": rationale
        }

    def compute_engineer_centrality(self, engineer_name: str, tenant_id: str = None) -> Dict[str, Any]:
        """Graph-centrality-based expertise scoring for one engineer."""
        tid = tenant_id or "default"
        
        q1 = """
        MATCH (p:Person {name: $name, tenant_id: $tid})-[r]-(n)
        RETURN count(r) AS degree, count(DISTINCT n) AS unique_connections
        """
        res1 = self.run_query(q1, {"name": engineer_name, "tid": tid})
        degree = res1[0]["degree"] if res1 else 0
        unique_connections = res1[0]["unique_connections"] if res1 else 0
        
        q2 = """
        MATCH (p:Person {name: $name, tenant_id: $tid})-[:KNOWLEDGE_OWNER_FOR|MAINTAINED_BY]->(a)
        WHERE exists((a)<-[:OCCURRED_ON]-(:Incident))
        RETURN count(a) AS critical_asset_count, collect(a.name) AS critical_assets
        """
        res2 = self.run_query(q2, {"name": engineer_name, "tid": tid})
        critical_asset_count = res2[0]["critical_asset_count"] if res2 else 0
        critical_assets = res2[0]["critical_assets"] if res2 else []
        
        q3 = """
        MATCH (p:Person {name: $name, tenant_id: $tid})-[:KNOWLEDGE_OWNER_FOR|MAINTAINED_BY]->(a)
        WHERE NOT exists {
          MATCH (other:Person {tenant_id: $tid})-[:KNOWLEDGE_OWNER_FOR|MAINTAINED_BY]->(a)
          WHERE other.name <> $name
        }
        RETURN count(a) AS sole_owned_assets, collect(a.name) AS sole_assets
        """
        res3 = self.run_query(q3, {"name": engineer_name, "tid": tid})
        sole_owned_assets = res3[0]["sole_owned_assets"] if res3 else 0
        sole_assets = res3[0]["sole_assets"] if res3 else []
        
        expertise_score = min(100, (
            degree * 2 +
            critical_asset_count * 10 +
            sole_owned_assets * 15
        ))
        
        succession_risk = "Critical" if sole_owned_assets >= 3 else \
                          "High"     if sole_owned_assets >= 1 else \
                          "Medium"   if critical_asset_count >= 2 else "Low"
                          
        return {
            "engineer": engineer_name,
            "expertise_score": expertise_score,
            "degree_centrality": degree,
            "unique_connections": unique_connections,
            "critical_asset_count": critical_asset_count,
            "critical_assets": critical_assets,
            "sole_owned_assets": sole_owned_assets,
            "sole_assets": sole_assets,
            "succession_risk": succession_risk,
            "risk_reason": f"Sole knowledge owner of {sole_owned_assets} assets" if sole_owned_assets > 0 else "Shared knowledge coverage"
        }

    def get_all_engineers(
        self,
        tenant_id: str = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Returns the names of all Person nodes in the graph for a given tenant,
        along with their expertise, centrality, succession risk, and connected assets.
        """
        tid = tenant_id or "default"
        query = """
        MATCH (p {tenant_id: $tenant_id})
        WHERE p.type = 'Person' OR 'Person' IN labels(p)
        WITH p, coalesce(p.name, p.label, p.canonical_name, 'Unknown Engineer') AS person_name

        // Count total relationships (degree) and unique connections
        OPTIONAL MATCH (p)-[r]-(n)
        WITH p, person_name, count(distinct r) as degree, count(distinct n) as unique_connections

        // Get all connected assets/equipment
        OPTIONAL MATCH (p)-[:MAINTAINED_BY|INSPECTED_BY|OPERATED_BY|KNOWLEDGE_OWNER|OWNED_BY|KNOWLEDGE_OWNER_FOR]-(a)
        WHERE (a:Asset OR a:Equipment) AND a.tenant_id = $tenant_id
        WITH p, person_name, degree, unique_connections, collect(distinct coalesce(a.name, a.label)) as assets

        // Count critical assets (assets connected to an Incident)
        OPTIONAL MATCH (p)-[:MAINTAINED_BY|INSPECTED_BY|OPERATED_BY|KNOWLEDGE_OWNER|OWNED_BY|KNOWLEDGE_OWNER_FOR]-(ca)
        WHERE (ca:Asset OR ca:Equipment) AND ca.tenant_id = $tenant_id
          AND exists((ca)<-[:OCCURRED_ON]-(:Incident))
        WITH p, person_name, degree, unique_connections, assets, count(distinct ca) as critical_asset_count

        // Count sole owned assets
        OPTIONAL MATCH (p)-[:MAINTAINED_BY|INSPECTED_BY|OPERATED_BY|KNOWLEDGE_OWNER|OWNED_BY|KNOWLEDGE_OWNER_FOR]-(sa)
        WHERE (sa:Asset OR sa:Equipment) AND sa.tenant_id = $tenant_id
          AND NOT exists((sa)<-[:MAINTAINED_BY|INSPECTED_BY|OPERATED_BY|KNOWLEDGE_OWNER|OWNED_BY|KNOWLEDGE_OWNER_FOR]-(other) WHERE other.tenant_id = $tenant_id AND (other.type = 'Person' OR 'Person' IN labels(other)) AND id(other) <> id(p))
        WITH p, person_name, degree, unique_connections, assets, critical_asset_count, count(distinct sa) as sole_owned_assets

        RETURN person_name as name, p.role as role, degree, unique_connections, assets, critical_asset_count, sole_owned_assets
        LIMIT $limit
        """
        params = {"tenant_id": tid, "limit": limit}
        
        try:
            rows = self.run_query(query, params)
        except Exception as e:
            logger.error(f"Failed listing engineers: {e}")
            return []
            
        results = []
        for row in rows:
            name = row.get("name")
            if name:
                degree = row.get("degree", 0)
                assets = row.get("assets", [])
                critical_asset_count = row.get("critical_asset_count", 0)
                sole_owned_assets = row.get("sole_owned_assets", 0)
                
                # Compute expertise score (max 100)
                expertise_score = min(100, (
                    degree * 2 +
                    critical_asset_count * 10 +
                    sole_owned_assets * 15
                ))
                
                # Compute succession risk
                succession_risk = "Critical" if sole_owned_assets >= 3 else \
                                  "High"     if sole_owned_assets >= 1 else \
                                  "Medium"   if critical_asset_count >= 2 else "Low"
                                  
                # Normalized centrality (degree / 100.0)
                centrality = round(degree / 100.0, 3)
                
                risk_reason = f"Sole knowledge owner of {sole_owned_assets} assets" if sole_owned_assets > 0 else "Shared knowledge coverage"
                
                results.append({
                    "name": name,
                    "role": row.get("role") or "Engineer",
                    "expertise_score": float(expertise_score),
                    "centrality": centrality,
                    "succession_risk": succession_risk,
                    "assets": assets,
                    "sole_owned_assets": sole_owned_assets,
                    "critical_asset_count": critical_asset_count,
                    "risk_reason": risk_reason
                })
                
        results.sort(key=lambda x: x.get("expertise_score", 0), reverse=True)
        return results

# Singleton instance
neo4j_client = Neo4jClient()
