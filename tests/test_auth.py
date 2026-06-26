import sys
import os
import unittest

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.auth import hash_password, verify_password, create_access_token
import jwt
from backend.config import get_settings

class TestAuth(unittest.TestCase):
    def test_password_hashing(self):
        password = "my_secure_password"
        hashed = hash_password(password)
        
        # Verify hash format
        self.assertIn(":", hashed)
        parts = hashed.split(":")
        self.assertEqual(len(parts), 2)
        
        # Verify valid password
        self.assertTrue(verify_password(password, hashed))
        
        # Verify invalid password
        self.assertFalse(verify_password("wrong_password", hashed))

    def test_jwt_generation(self):
        settings = get_settings()
        data = {"sub": "testuser", "role": "engineer"}
        token = create_access_token(data)
        
        # Decode and verify
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        self.assertEqual(payload["sub"], "testuser")
        self.assertEqual(payload["role"], "engineer")
        self.assertIn("exp", payload)

if __name__ == '__main__':
    unittest.main()
