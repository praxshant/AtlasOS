import uuid
import pytest

def test_register_and_login(client):
    unique_id = uuid.uuid4().hex[:8]
    email = f"test_{unique_id}@example.com"
    password = "securepassword123"
    
    # 1. Register
    reg_response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "username": f"user_{unique_id}",
            "name": "Test User",
            "role": "engineer"
        }
    )
    assert reg_response.status_code == 201, f"Registration failed: {reg_response.text}"
    data = reg_response.json()
    assert "message" in data
    
    # 2. Login
    login_response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password}
    )
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    login_data = login_response.json()
    assert "access_token" in login_data
    assert login_data["token_type"] == "bearer"
    
    # 3. Protected Route (e.g. system integrity or dashboard stats)
    headers = {"Authorization": f"Bearer {login_data['access_token']}"}
    stats_response = client.get("/api/stats", headers=headers)
    assert stats_response.status_code == 200, "Protected route access failed"

def test_tenant_isolation(client, setup_tenant_and_user, auth_headers):
    # The authenticated user belongs to setup_tenant_and_user["tenant_id"]
    # Verify that requesting system integrity defaults to their tenant
    integrity_response = client.get("/api/system/integrity", headers=auth_headers)
    assert integrity_response.status_code == 200
    data = integrity_response.json()
    assert data["tenant_id"] == setup_tenant_and_user["tenant_id"]
