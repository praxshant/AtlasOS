import os
import sys
import json
from datetime import datetime

# Add the project root to sys.path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.db.postgres import SessionLocal, Document, Chunk, Entity, ProcessingJob
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client
from backend.config import get_settings

settings = get_settings()

def investigate():
    results = {}
    
    # 1. Postgres - Documents
    db = SessionLocal()
    docs = db.query(Document).all()
    results["documents"] = [
        {"id": d.id, "filename": d.filename, "status": d.status, "tenant_id": d.tenant_id}
        for d in docs
    ]
    
    # 2. Postgres - Chunks
    chunks = db.query(Chunk).all()
    results["postgres_chunks"] = len(chunks)
    
    # 3. Postgres - Entities
    entities = db.query(Entity).all()
    results["postgres_entities"] = len(entities)
    
    # 4. Neo4j - Nodes and Edges
    try:
        nodes = neo4j_client.run_query("MATCH (n) RETURN labels(n) as label, n.name as name")
        edges = neo4j_client.run_query("MATCH ()-[r]->() RETURN type(r) as type")
        results["neo4j"] = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes
        }
    except Exception as e:
        results["neo4j"] = {"error": str(e)}

    # 5. Qdrant
    try:
        q_info = qdrant_client.client.get_collection(settings.QDRANT_COLLECTION_NAME)
        results["qdrant"] = {
            "status": q_info.status,
            "vectors_count": q_info.vectors_count,
            "segments_count": q_info.segments_count
        }
    except Exception as e:
         results["qdrant"] = {"error": str(e)}

    db.close()
    
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    investigate()
