import os
import sys
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlmodel import select

# Ensure backend root is in sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dependencies import get_current_user
from models import User
from tests.conftest import get_test_engine, get_test_session


class TestDependencies(unittest.TestCase):
    def setUp(self):
        self.engine = get_test_engine()
        self.session = get_test_session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_jit_user_provisioning_creates_new_user(self):
        """Tailscale Identity automatically provisions users just-in-time with profile picture."""
        user = get_current_user(
            tailscale_user_login="alice@tailnet.ts.net",
            tailscale_user_name="Alice Tailscale",
            tailscale_user_profile_pic="https://tailscale.com/avatar/alice.png",
            session=self.session,
        )
        self.assertIsNotNone(user.id)
        self.assertEqual(user.login, "alice@tailnet.ts.net")
        self.assertEqual(user.name, "Alice Tailscale")
        self.assertEqual(user.profile_pic, "https://tailscale.com/avatar/alice.png")

        # Verify persisted in database
        db_user = self.session.exec(select(User).where(User.login == "alice@tailnet.ts.net")).first()
        self.assertIsNotNone(db_user)
        self.assertEqual(db_user.id, user.id)
        self.assertEqual(db_user.profile_pic, "https://tailscale.com/avatar/alice.png")

    def test_jit_user_updates_display_name_on_change(self):
        """Changing Tailscale-User-Name updates existing user record."""
        get_current_user(
            tailscale_user_login="bob@tailnet.ts.net",
            tailscale_user_name="Bob Original",
            tailscale_user_profile_pic=None,
            session=self.session,
        )
        updated = get_current_user(
            tailscale_user_login="bob@tailnet.ts.net",
            tailscale_user_name="Bob Updated",
            tailscale_user_profile_pic=None,
            session=self.session,
        )
        self.assertEqual(updated.name, "Bob Updated")

    def test_jit_user_updates_profile_pic_on_change(self):
        """Changing Tailscale-User-Profile-Pic updates existing user record."""
        get_current_user(
            tailscale_user_login="carol@tailnet.ts.net",
            tailscale_user_name="Carol",
            tailscale_user_profile_pic="https://example.com/pic1.jpg",
            session=self.session,
        )
        updated = get_current_user(
            tailscale_user_login="carol@tailnet.ts.net",
            tailscale_user_name="Carol",
            tailscale_user_profile_pic="https://example.com/pic2.jpg",
            session=self.session,
        )
        self.assertEqual(updated.profile_pic, "https://example.com/pic2.jpg")

    def test_tailscale_missing_header_raises_401_when_not_dev(self):
        """Requests without Tailscale headers are rejected with 401 when dev mode is disabled."""
        with patch("dependencies.DEV_MODE", False):
            with self.assertRaises(HTTPException) as ctx:
                get_current_user(
                    tailscale_user_login=None,
                    tailscale_user_name=None,
                    tailscale_user_profile_pic=None,
                    session=self.session,
                )
            self.assertEqual(ctx.exception.status_code, 401)

    def test_dev_mode_fallback_identity(self):
        """When DEV_MODE is True, missing headers fall back to DEV_USER config values."""
        with patch("dependencies.DEV_MODE", True), \
             patch("dependencies.DEV_USER_LOGIN", "dev@custom.local"), \
             patch("dependencies.DEV_USER_NAME", "Custom Dev"), \
             patch("dependencies.DEV_USER_PROFILE_PIC", "https://custom.local/dev.png"):
            user = get_current_user(
                tailscale_user_login=None,
                tailscale_user_name=None,
                tailscale_user_profile_pic=None,
                session=self.session,
            )
            self.assertEqual(user.login, "dev@custom.local")
            self.assertEqual(user.name, "Custom Dev")
            self.assertEqual(user.profile_pic, "https://custom.local/dev.png")


if __name__ == "__main__":
    unittest.main()
