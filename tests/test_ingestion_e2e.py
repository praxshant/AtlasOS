import os
import sys
import time
import uuid
from sqlalchemy import text

# Ensure project root is in sys.path
sys.path.append(r"c:\Users\ACER\OneDrive\Desktop\AtlasOS")

from backend.db.postgres import SessionLocal, Document, ProcessingJob, Chunk, Entity, Tenant, init_db
from backend.tasks.ingestion_tasks import process_document_task
from backend.tasks.progress_tracker import progress_tracker
from backend.vector.qdrant_client import qdrant_client
from backend.graph.neo4j_client import neo4j_client
from backend.config import get_settings

def run_test():
    print("Starting End-to-End Ingestion Validation...")
    
    # Initialize DB schema
    init_db()
    print("Postgres database tables initialized.")
    
    db = SessionLocal()
    tenant_id = "test-tenant-e2e-" + str(uuid.uuid4())[:8]
    print(f"Using tenant_id: {tenant_id}")
    
    # Ensure Tenant exists in Postgres due to FK constraints
    tenant = Tenant(id=tenant_id, name=f"Test Tenant {tenant_id}", slug=f"test-{tenant_id}")
    db.add(tenant)
    db.commit()
    print(f"Created Tenant record for {tenant_id}.")
    
    # 1. Create a sample txt file
    content = "Pump P-101 is maintained by Ramesh Kumar. A seal leak occurred on Pump P-101. This seal leak relates to SOP-201."
    filename = f"test_e2e_{uuid.uuid4().hex[:8]}.txt"
    upload_dir = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Created sample document: {file_path}")
    
    # 2. Create Postgres records
    db_doc = Document(
        tenant_id=tenant_id,
        filename=filename,
        file_path=file_path,
        file_type="TXT",
        status="pending",
        source="e2e_test"
    )
    db.add(db_doc)
    db.flush()
    doc_id = db_doc.id
    
    job_id = str(uuid.uuid4())
    db_job = ProcessingJob(
        id=job_id,
        tenant_id=tenant_id,
        document_id=doc_id,
        status="pending"
    )
    db.add(db_job)
    db.commit()
    print(f"Created Document record (ID: {doc_id}) and ProcessingJob record (ID: {job_id}) in Postgres.")
    
    # 3. Dispatch Celery task
    print("Dispatching Celery task...")
    result = process_document_task.delay(job_id, tenant_id)
    print(f"Task dispatched with celery ID: {result.id}")
    
    # 4. Wait for processing (polling Redis & Postgres)
    print("Waiting for task to complete...")
    max_wait = 60 # 60 seconds max
    start_time = time.time()
    job_status = "pending"
    
    while time.time() - start_time < max_wait:
        db.refresh(db_job)
        job_status = db_job.status
        print(f"Current Job Status: {job_status}")
        
        # Check Redis progress
        progress = progress_tracker.get_progress(job_id)
        print(f"Redis Progress: {progress}")
        
        if job_status in ["completed", "failed"]:
            break
        time.sleep(2)
        
    if job_status != "completed":
        print(f"RCA/Ingestion failed or timed out! Final Status: {job_status}, Error: {db_job.error}")
        db.close()
        sys.exit(1)
        
    print("[OK] ProcessingJob status in Postgres is completed.")
    
    # 5. Verify Postgres records
    chunks = db.query(Chunk).filter(Chunk.document_id == doc_id, Chunk.tenant_id == tenant_id).all()
    print(f"Found {len(chunks)} chunks in Postgres for this document.")
    assert len(chunks) > 0, "No chunks created in Postgres!"
    for c in chunks:
        print(f" - Chunk index: {c.chunk_index}, page: {c.page_number}, text length: {len(c.text_content)}")
        
    entities = db.query(Entity).filter(Entity.source_doc_id == doc_id, Entity.tenant_id == tenant_id).all()
    print(f"Found {len(entities)} entities in Postgres for this document.")
    
    # Note: LLM extraction might extract assets like Pump P-101
    
    # 6. Verify Qdrant vectors
    settings = get_settings()
    collection = settings.QDRANT_COLLECTION_NAME
    scored_points = qdrant_client.similarity_search(
        collection_name=collection,
        query="Pump P-101",
        top_k=5,
        filter_doc_id=doc_id,
        tenant_id=tenant_id
    )
    print(f"Found {len(scored_points)} points in Qdrant collection '{collection}' matching the document and tenant.")
    assert len(scored_points) > 0, "No points found in Qdrant!"
    for p in scored_points:
        print(f" - Point: {p['id']}, Score: {p['score']}, Text: '{p['text']}'")
        
    # 7. Verify Neo4j nodes & relationships
    neo4j_nodes = neo4j_client.run_query(
        "MATCH (n) WHERE n.tenant_id = $tenant_id RETURN n.name as name, labels(n)[0] as label",
        {"tenant_id": tenant_id}
    )
    print(f"Found {len(neo4j_nodes)} nodes in Neo4j for tenant {tenant_id}:")
    for node in neo4j_nodes:
        print(f" - Node: {node['name']} ({node['label']})")
        
    neo4j_rels = neo4j_client.run_query(
        "MATCH (n)-[r]->(m) WHERE r.tenant_id = $tenant_id RETURN n.name as source, type(r) as type, m.name as target",
        {"tenant_id": tenant_id}
    )
    print(f"Found {len(neo4j_rels)} relationships in Neo4j for tenant {tenant_id}:")
    for rel in neo4j_rels:
        print(f" - Relationship: ({rel['source']}) -[{rel['type']}]-> ({rel['target']})")
        
    # Cleanup files
    try:
        os.remove(file_path)
    except Exception:
        pass
        
    db.close()
    print("ALL END-TO-END VALIDATION CHECKS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_test()
