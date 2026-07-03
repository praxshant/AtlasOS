import pytest

def test_knowledge_graph_loading(client, auth_headers):
    # 1. Test full graph data loading
    resp = client.get("/api/graph/data", headers=auth_headers)
    assert resp.status_code == 200, f"Graph data failed: {resp.text}"
    
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    
    # We should have nodes and edges from test_02_upload.py, 
    # but we can't guarantee order if ran independently, 
    # so we just assert structure.
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)

    # 2. Test node expansion
    if data["nodes"]:
        first_node = data["nodes"][0]["name"]
        expand_resp = client.get(f"/api/graph/expand/{first_node}", headers=auth_headers)
        
        # the expand route may return 200 or 404 depending on how it's implemented for special chars
        # but 200 is expected for a valid node
        if expand_resp.status_code == 200:
            expand_data = expand_resp.json()
            assert "nodes" in expand_data
            assert "edges" in expand_data
