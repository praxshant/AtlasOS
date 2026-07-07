import os

file_path = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\backend\graph\neo4j_client.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

new_methods = """
    @property
    def driver(self):
        return self.get_driver()

    def ensure_constraints(self):
        with self.get_driver().session() as s:
            s.run(
                "CREATE CONSTRAINT unique_entity IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE (e.tenant_id, e.canonical_id) IS UNIQUE"
            )

    def bulk_upsert(self, tenant_id: str, entities: list[dict], relationships: list[dict]) -> dict:
        node_query_no_apoc = '''
        UNWIND $entities AS e
        MERGE (n:Entity {tenant_id: $tenant_id, canonical_id: e.canonical_id})
        SET n.name = e.name,
            n.type = e.type,
            n.document_id = e.document_id,
            n.confidence = coalesce(e.confidence, 0.8),
            n.extraction_method = coalesce(e.extraction_method, 'llm'),
            n.updated_at = timestamp()
        RETURN count(n) AS nodes
        '''

        rel_query = '''
        UNWIND $rels AS r
        MATCH (a:Entity {tenant_id: $tenant_id, canonical_id: r.source})
        MATCH (b:Entity {tenant_id: $tenant_id, canonical_id: r.target})
        WHERE elementId(a) <> elementId(b)
        MERGE (a)-[rel:REL {rel_type: r.type}]->(b)
        SET rel.tenant_id = $tenant_id,
            rel.document_id = r.document_id,
            rel.confidence = coalesce(r.confidence, 0.7),
            rel.updated_at = timestamp()
        RETURN count(rel) AS edges
        '''

        def _tx(tx):
            nodes = tx.run(
                node_query_no_apoc,
                entities=entities,
                tenant_id=tenant_id,
            ).single()["nodes"]
            edges = 0
            if relationships:
                edges = tx.run(
                    rel_query,
                    rels=relationships,
                    tenant_id=tenant_id,
                ).single()["edges"]
            return {"nodes_upserted": nodes, "edges_upserted": edges}

        with self.get_driver().session() as session:
            return session.execute_write(_tx)

    def get_stats(self, tenant_id: str = "default") -> dict:
        with self.get_driver().session() as session:
            rec = session.run(
                '''
                MATCH (n:Entity {tenant_id: $tid})
                OPTIONAL MATCH (n)-[r]->()
                RETURN count(DISTINCT n) AS nodes, count(r) AS edges
                ''',
                tid=tenant_id,
            ).single()
            return {"graph_nodes": rec["nodes"], "graph_edges": rec["edges"]}
"""

# Insert right before neo4j_client = Neo4jClient() if it exists at the bottom
if "neo4j_client = Neo4jClient()" in content:
    content = content.replace("neo4j_client = Neo4jClient()", new_methods + "\n\nneo4j_client = Neo4jClient()")
else:
    # Just append
    content += "\n" + new_methods

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched neo4j_client.py")
