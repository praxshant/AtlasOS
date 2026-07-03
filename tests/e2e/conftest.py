import pytest
import uuid
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient
from backend.app import app
from backend.db.postgres import SessionLocal, init_db, Tenant, User
from backend.utils.auth import hash_password

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="session")
def e2e_tenant_id():
    return f"e2e-tenant-{uuid.uuid4().hex[:6]}"

@pytest.fixture(scope="session")
def setup_tenant_and_user(client, e2e_tenant_id):
    db = SessionLocal()
    try:
        # Create tenant
        tenant = Tenant(id=e2e_tenant_id, name=f"E2E Test Tenant", slug=e2e_tenant_id)
        db.add(tenant)
        db.commit()

        # Create user
        email = f"admin@{e2e_tenant_id}.com"
        password = "testpassword123"
        user = User(
            email=email,
            username=f"admin_{e2e_tenant_id}",
            hashed_password=hash_password(password),
            tenant_id=e2e_tenant_id,
            role="admin"
        )
        db.add(user)
        db.commit()

        return {"email": email, "password": password, "tenant_id": e2e_tenant_id}
    finally:
        db.close()

@pytest.fixture(scope="session")
def auth_headers(client, setup_tenant_and_user):
    user_info = setup_tenant_and_user
    response = client.post(
        "/api/auth/login",
        json={"email": user_info["email"], "password": user_info["password"]},
    )
    assert response.status_code == 200, "Failed to authenticate test user"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
