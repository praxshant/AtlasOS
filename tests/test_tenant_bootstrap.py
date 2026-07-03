import sys
import os
import unittest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.postgres import SessionLocal, Tenant, User, init_db, ensure_default_tenant
from backend.app import app

class TestTenantBootstrap(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        from backend.config import get_settings
        self.settings = get_settings()
        self.original_tenant_id = self.settings.DEFAULT_TENANT_ID
        self.settings.DEFAULT_TENANT_ID = "test_bootstrap_tenant"
        
        # Clean up existing test records to avoid conflicts
        self.db.query(User).filter(User.username == "bootstrap_user").delete()
        self.db.query(Tenant).filter(Tenant.id == "test_bootstrap_tenant").delete()
        self.db.commit()
        self.client = TestClient(app)

    def tearDown(self):
        # Clean up after tests
        self.db.query(User).filter(User.username == "bootstrap_user").delete()
        self.db.query(Tenant).filter(Tenant.id == "test_bootstrap_tenant").delete()
        self.db.commit()
        self.settings.DEFAULT_TENANT_ID = self.original_tenant_id
        self.db.close()

    def test_fresh_db_startup_creates_default_tenant(self):
        # Run ensure_default_tenant directly to simulate bootstrap
        ensure_default_tenant()
        
        # Verify that default tenant exists
        default_tenant = self.db.query(Tenant).filter(Tenant.id == "default").first()
        self.assertIsNotNone(default_tenant)
        self.assertEqual(default_tenant.name, "Default Organization")
        self.assertEqual(default_tenant.slug, "default")

    def test_registration_succeeds_and_references_default_tenant(self):
        # Bootstrap database and default tenant
        init_db()
        
        # Call registration endpoint using TestClient
        payload = {
            "username": "bootstrap_user",
            "email": "bootstrap@test.com",
            "password": "Password123",
            "role": "engineer"
        }
        response = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, 201)
        
        # Verify user row was created and references the default tenant
        user = self.db.query(User).filter(User.username == "bootstrap_user").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.tenant_id, self.settings.DEFAULT_TENANT_ID)

if __name__ == '__main__':
    unittest.main()
