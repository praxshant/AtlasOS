import pytest

def test_dashboard_endpoints(client, auth_headers):
    # 1. Test unified dashboard endpoint
    dash_resp = client.get("/api/dashboard", headers=auth_headers)
    assert dash_resp.status_code == 200, f"Dashboard unified failed: {dash_resp.text}"
    
    dash_data = dash_resp.json()
    assert "metrics" in dash_data
    assert "activity" in dash_data
    assert "health" in dash_data
    
    # 2. Test individual stats endpoint
    stats_resp = client.get("/api/stats", headers=auth_headers)
    assert stats_resp.status_code == 200, f"Stats failed: {stats_resp.text}"
    
    stats = stats_resp.json()
    assert "total_documents" in stats
    assert "total_chunks" in stats
    assert "graph_nodes" in stats
    assert "system_health" in stats
    
    # 3. Test individual health endpoint
    health_resp = client.get("/api/system/health", headers=auth_headers)
    assert health_resp.status_code == 200
    health = health_resp.json()
    assert "neo4j" in health
    assert "postgresql" in health
    assert "qdrant" in health
    
    # 4. Test activity endpoint
    activity_resp = client.get("/api/dashboard/activity", headers=auth_headers)
    assert activity_resp.status_code == 200
    activity = activity_resp.json()
    assert isinstance(activity, list)
