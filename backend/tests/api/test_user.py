"""Tests for the user (Tailscale identity) endpoint."""

import unittest

from fastapi.testclient import TestClient

import app.config as cfg
from app.dependencies.db import get_db
from app.dependencies.tailscale import get_current_user
from app.main import app
from app.models.user import User
from tests.conftest import get_test_engine, get_test_session


class TestUserEndpoint(unittest.TestCase):
    def setUp(self):
        self.engine = get_test_engine()
        self.session = get_test_session(self.engine)
        self.user = User(login="me@example.test", name="Me", email="me@example.test", profile_pic="pic")
        self.session.add(self.user)
        self.session.commit()

        def override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.session.close()

    def test_profile_returns_identity(self):
        resp = self.client.get("/api/user")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["login"], "me@example.test")
        self.assertEqual(body["name"], "Me")
        self.assertEqual(body["profile_pic"], "pic")

    def test_root_and_me_routes_agree(self):
        self.assertEqual(self.client.get("/api/user").json()["login"], "me@example.test")

    def test_missing_tailscale_header_rejects_when_dev_disabled(self):
        original = cfg.settings.dev_mode
        cfg.settings.dev_mode = False
        app.dependency_overrides.clear()
        try:
            client = TestClient(app)
            self.assertEqual(client.get("/api/user").status_code, 401)
        finally:
            cfg.settings.dev_mode = original
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
