import pytest
import os
from unittest.mock import patch, MagicMock

# Set required env vars for testing before importing modules
os.environ["OPENROUTER_API_KEY"] = "test_key"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["QDRANT_URL"] = "http://localhost:6333"

from backend.db.postgres import SessionLocal, Tenant, User, Document, Chunk, Entity, ProcessingJob
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client

def test_tenant_isolation_postgres():
    # Verify that we can't fetch tenant B's data when querying with tenant A
    db = SessionLocal()
    
    # Clean up t1 and t2 only to avoid foreign key violations on other tenants (like default)
    db.query(ProcessingJob).filter(ProcessingJob.tenant_id.in_(["t1", "t2"])).delete(synchronize_session=False)
    db.query(Chunk).filter(Chunk.tenant_id.in_(["t1", "t2"])).delete(synchronize_session=False)
    db.query(Entity).filter(Entity.tenant_id.in_(["t1", "t2"])).delete(synchronize_session=False)
    db.query(Document).filter(Document.tenant_id.in_(["t1", "t2"])).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id.in_(["t1", "t2"])).delete(synchronize_session=False)
    db.query(Tenant).filter(Tenant.id.in_(["t1", "t2"])).delete(synchronize_session=False)
    
    # Create tenants
    t1 = Tenant(id="t1", name="Tenant 1", slug="t1")
    t2 = Tenant(id="t2", name="Tenant 2", slug="t2")
    db.add(t1)
    db.add(t2)
    db.commit()
    
    # Create docs
    d1 = Document(tenant_id="t1", filename="doc1.pdf", file_path="doc1.pdf", file_type="PDF", status="completed")
    d2 = Document(tenant_id="t2", filename="doc2.pdf", file_path="doc2.pdf", file_type="PDF", status="completed")
    db.add(d1)
    db.add(d2)
    db.commit()
    
    # Query docs for t1
    docs_t1 = db.query(Document).filter(Document.tenant_id == "t1").all()
    assert len(docs_t1) == 1
    assert docs_t1[0].filename == "doc1.pdf"
    
    db.close()

def test_tenant_isolation_neo4j():
    # Verify Cypher queries filter by tenant
    neo4j_client.init_indexes()
    
    # Clean up
    neo4j_client.run_query("MATCH (n) DETACH DELETE n")
    
    # Insert with tenants
    neo4j_client.run_query("CREATE (n:Entity {name: 'Pump-A', tenant_id: 't1'})")
    neo4j_client.run_query("CREATE (n:Entity {name: 'Pump-B', tenant_id: 't2'})")
    
    # Search nodes
    res_t1 = neo4j_client.search_nodes("Pump", tenant_id="t1")
    assert len(res_t1) == 1
    assert res_t1[0]["name"] == "Pump-A"
    
    res_t2 = neo4j_client.search_nodes("Pump", tenant_id="t2")
    assert len(res_t2) == 1
    assert res_t2[0]["name"] == "Pump-B"
    
def test_tenant_isolation_qdrant():
    # Note: Qdrant must be running to test this properly
    # Using a mock for qdrant client methods to verify filters are built correctly
    with patch.object(qdrant_client, 'get_client') as mock_client:
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance
        
        # Test similarity_search passes tenant_id filter
        qdrant_client.similarity_search("test_col", "query", tenant_id="t1")
        
        # Verify the call to query_points has the correct filter
        args, kwargs = mock_client_instance.query_points.call_args
        assert kwargs["query_filter"] is not None
        # Must have condition checking tenant_id = "t1"
        conditions = kwargs["query_filter"].must
        has_tenant = False
        for cond in conditions:
            if getattr(cond, 'key', '') == "tenant_id" and cond.match.value == "t1":
                has_tenant = True
        assert has_tenant

if __name__ == "__main__":
    pytest.main(["-v", __file__])
