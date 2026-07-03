from backend.db.postgres import SessionLocal, Document, Chunk, Entity
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client

def purge():
    db = SessionLocal()
    try:
        # Delete from Postgres
        stuck_docs = db.query(Document).filter(Document.status.in_(["deleting", "failed_delete"])).all()
        for doc in stuck_docs:
            print(f"Purging stuck doc {doc.id}")
            db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
            db.delete(doc)
            db.commit()

        # Wipe Neo4j since it's just test data and the user wants to start fresh
        print("Wiping Neo4j")
        neo4j_client.run_query("MATCH (n) DETACH DELETE n")

        # Wipe Qdrant
        print("Wiping Qdrant")
        try:
            qdrant_client.get_client().delete_collection(qdrant_client.collection_name)
            qdrant_client._ensure_collection_exists()
        except Exception as e:
            print("Failed to wipe Qdrant", e)
            pass

    finally:
        db.close()

if __name__ == "__main__":
    purge()
