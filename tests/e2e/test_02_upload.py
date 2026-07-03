import os
import time
import pytest

def test_document_ingestion_pipeline(client, auth_headers, setup_tenant_and_user):
    tenant_id = setup_tenant_and_user["tenant_id"]
    
    # 1. Upload a document
    file_content = b"Pump P-101 failed due to seal leak on 2024-01-05. Reported by John Doe."
    files = {"file": ("test_e2e_incident.txt", file_content, "text/plain")}
    
    upload_resp = client.post("/api/upload", headers=auth_headers, files=files)
    assert upload_resp.status_code == 202, f"Upload failed: {upload_resp.text}"
    
    data = upload_resp.json()
    job_id = data["job_id"]
    assert job_id is not None
    
    # 2. Poll for completion
    max_wait = 45
    start = time.time()
    completed = False
    
    while time.time() - start < max_wait:
        status_resp = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        
        if status_data["status"] == "completed":
            completed = True
            break
        elif status_data["status"] == "failed":
            pytest.fail(f"Ingestion job failed: {status_data.get('error')}")
            
        time.sleep(2)
        
    assert completed, "Document ingestion timed out."
    
    # 3. Verify Databases via Integrity Checker
    integrity_resp = client.get("/api/system/integrity", headers=auth_headers)
    assert integrity_resp.status_code == 200
    integrity = integrity_resp.json()
    
    metrics = integrity["metrics"]
    assert metrics["postgres"]["completed_documents"] > 0
    assert metrics["postgres"]["chunks"] > 0
    assert metrics["postgres"]["entities"] > 0
    assert metrics["qdrant"]["vectors"] > 0
    assert metrics["neo4j"]["nodes"] > 0
    
    # 4. Verify Dashboard Metrics reflect the upload
    stats_resp = client.get("/api/stats", headers=auth_headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    
    assert stats["total_documents"] >= 1
    assert stats["graph_nodes"] > 0
    assert stats["graph_edges"] >= 0
