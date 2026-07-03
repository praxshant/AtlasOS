import pytest

def test_compliance_check(client, auth_headers):
    # Retrieve a document ID first, or just use 999 if it handles invalid docs gracefully 
    # (actually it probably queries the DB, so let's get a real doc ID from stats/documents)
    
    docs_resp = client.get("/api/documents", headers=auth_headers)
    assert docs_resp.status_code == 200
    docs = docs_resp.json()
    
    if not docs:
        pytest.skip("No documents available to test compliance")
        
    doc_id = docs[0]["id"]
    
    payload = {
        "document_id": doc_id,
        "regulation_scope": "OSHA 1910.119"
    }
    
    resp = client.post("/api/compliance/check", json=payload, headers=auth_headers)
    assert resp.status_code == 200, f"Compliance check failed: {resp.text}"
    
    data = resp.json()
    assert "compliance_score" in data
    assert "gaps" in data
    assert isinstance(data["gaps"], list)
