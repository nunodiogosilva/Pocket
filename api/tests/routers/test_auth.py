import os
import sys
import unittest
from fastapi.testclient import TestClient

# Ensure API root is in sys.path
API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from main import app
from models import FileMeta, User
from dependencies import get_current_user, get_db
from tests.conftest import get_test_engine, get_test_session


class TestAuthRouter(unittest.TestCase):
    def setUp(self):
        self.engine = get_test_engine()
        self.session = get_test_session(self.engine)
        self.test_user = User(
            id=1,
            login="testuser@tailnet.ts.net",
            name="Test User",
            email="testuser@tailnet.ts.net",
            profile_pic="https://example.com/test_avatar.jpg",
        )
        self.session.add(self.test_user)
        self.session.commit()
        self.session.refresh(self.test_user)

        # Override dependencies
        def override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: self.test_user
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.session.close()

    def test_get_current_user_profile_at_me(self):
        """GET /api/auth/me returns the authenticated user profile with profile_pic."""
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.test_user.id)
        self.assertEqual(data["login"], "testuser@tailnet.ts.net")
        self.assertEqual(data["name"], "Test User")
        self.assertEqual(data["email"], "testuser@tailnet.ts.net")
        self.assertEqual(data["profile_pic"], "https://example.com/test_avatar.jpg")

    def test_get_current_user_profile_at_base(self):
        """GET /api/auth returns the authenticated user profile with profile_pic."""
        response = self.client.get("/api/auth")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.test_user.id)
        self.assertEqual(data["profile_pic"], "https://example.com/test_avatar.jpg")

    def test_get_current_user_storage(self):
        """GET /api/auth/storage returns storage metrics for the user."""
        # Add a file for user
        f1 = FileMeta(
            filename="testfile.dat",
            storage_path="",
            file_size=4096,
            mime_type="application/octet-stream",
            owner_id=self.test_user.id,
        )
        self.session.add(f1)
        self.session.commit()

        response = self.client.get("/api/auth/storage")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["used_bytes"], 4096)
        self.assertEqual(data["file_count"], 1)
        self.assertIn("total_bytes", data)


if __name__ == "__main__":
    unittest.main()
