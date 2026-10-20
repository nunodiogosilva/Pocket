import os
import sys
import unittest

# Ensure API root is in sys.path
API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from models import User


class TestUserModel(unittest.TestCase):
    def test_user_model_has_no_password_fields(self):
        """Traditional login/password hashing fields must not exist in User model."""
        user_fields = User.model_fields if hasattr(User, "model_fields") else getattr(User, "__fields__", {})
        self.assertNotIn("hashed_password", user_fields)
        self.assertNotIn("password", user_fields)
        self.assertNotIn("salt", user_fields)

    def test_user_model_fields(self):
        """User model contains login, name, profile_pic, email, and created_at fields."""
        user_fields = User.model_fields if hasattr(User, "model_fields") else getattr(User, "__fields__", {})
        self.assertIn("login", user_fields)
        self.assertIn("name", user_fields)
        self.assertIn("profile_pic", user_fields)
        self.assertIn("email", user_fields)
        self.assertIn("created_at", user_fields)

    def test_user_instantiation_with_profile_pic(self):
        """User can be instantiated with profile_pic and defaults correctly."""
        user = User(
            login="test@tailnet.ts.net",
            name="Test User",
            profile_pic="https://example.com/avatar.png",
        )
        self.assertEqual(user.login, "test@tailnet.ts.net")
        self.assertEqual(user.name, "Test User")
        self.assertEqual(user.profile_pic, "https://example.com/avatar.png")
        self.assertIsNone(user.email)
        self.assertIsNotNone(user.created_at)


if __name__ == "__main__":
    unittest.main()
