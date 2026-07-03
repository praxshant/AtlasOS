import pytest

def test_risk_assets(client, auth_headers):
    resp = client.get("/api/risk/assets", headers=auth_headers)
    assert resp.status_code == 200, f"Risk assets failed: {resp.text}"
    
    data = resp.json()
    assert isinstance(data, list)
    
    if data:
        asset = data[0]
        assert "asset_name" in asset
        assert "asset_type" in asset
        assert "factors" in asset
        
        # Test timeline for an asset
        asset_name = asset["asset_name"]
        tl_resp = client.get(f"/api/risk/timeline?asset={asset_name}", headers=auth_headers)
        if tl_resp.status_code == 200:
            tl_data = tl_resp.json()
            assert "events" in tl_data
            assert isinstance(tl_data["events"], list)
