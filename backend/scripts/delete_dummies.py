from backend.db.postgres import SessionLocal
from backend.graph.neo4j_client import neo4j_client

print("Deleting John Doe and Alice Smith...")
neo4j_client.run_query("MATCH (p:Person) WHERE p.name IN ['John Doe', 'Alice Smith'] DETACH DELETE p")

print("Deleting unwanted document nodes...")
neo4j_client.run_query("MATCH (n) WHERE n.name IN ['Mission Statement', 'Vendor Manual Extract', 'Section 1', 'Section 4', 'Internal PM Manual'] DETACH DELETE n")

print("Dummy nodes deleted.")
