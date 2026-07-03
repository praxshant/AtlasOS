import pytest

def test_copilot_query(client, auth_headers):
    payload = {
        "query": "Why did Pump P-101 fail?",
        "history": []
    }
    
    resp = client.post("/api/copilot/query", json=payload, headers=auth_headers)
    assert resp.status_code == 200, f"Copilot query failed: {resp.text}"
    
    # The Copilot endpoint is expected to stream server-sent events, but TestClient 
    # receives the complete response string which we can parse as SSE lines.
    text_data = resp.text
    
    assert "data:" in text_data, "Response should be Server-Sent Events containing 'data:'"
    
    # We should also check for a 'complete' event containing sources
    assert '"type": "done"' in text_data or '"type":"done"' in text_data, "Stream should emit a done event."

def test_copilot_suggestions(client, auth_headers):
    resp = client.get("/api/copilot/suggestions", headers=auth_headers)
    assert resp.status_code == 200
    
    data = resp.json()
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)
