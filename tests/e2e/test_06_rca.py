import pytest

def test_rca_generation(client, auth_headers):
    payload = {
        "incident_description": "Pump P-101 failed due to seal leak."
    }
    
    resp = client.post("/api/rca/run", json=payload, headers=auth_headers)
    assert resp.status_code == 200, f"RCA failed: {resp.text}"
    
    data = resp.json()
    assert "incident_title" in data
    assert "primary_cause" in data
    assert "fault_tree" in data
    assert isinstance(data["fault_tree"], list)
