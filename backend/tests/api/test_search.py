"""Tests for the semantic search endpoint and service (model-dependent parts mocked)."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.dependencies.db import get_db
from app.dependencies.tailscale import get_current_user
from app.main import app
from app.models.item import FileChunk, Item
from app.models.user import User
from app.services import search_service
from tests.conftest import get_test_engine, get_test_session


class TestSearchService(unittest.TestCase):
    def setUp(self):
        self.engine = get_test_engine()
        self.session = get_test_session(self.engine)
        self.user = User(login="owner@example.test", name="Owner")
        self.session.add(self.user)
        self.session.commit()
        self.session.refresh(self.user)

    def tearDown(self):
        self.session.close()

    def test_empty_query_short_circuits(self):
        with patch.object(search_service, "embed") as embed:
            self.assertEqual(search_service.search(self.session, self.user, "   ", 10), [])
            embed.assert_not_called()

    def test_make_snippet_caps_and_keeps_context(self):
        text = "start " + ("unrelated " * 30) + "needle " + ("more " * 40)
        snippet = search_service.make_snippet(text, ["needle"])
        self.assertIn("needle", snippet)
        self.assertTrue(snippet.startswith("..."))
        self.assertTrue(snippet.endswith("..."))
        self.assertIsNone(search_service.make_snippet("   ", ["word"]))

    def test_extract_text_skips_binary_and_media(self):
        import tempfile

        with tempfile.NamedTemporaryFile() as fh:
            fh.write(b"plain text\x00binary")
            fh.flush()
            self.assertEqual(search_service.extract_text(fh.name, "data.bin", "application/octet-stream"), "")
            self.assertEqual(search_service.extract_text(fh.name, "photo.jpg", "image/jpeg"), "")

    def test_extract_text_reads_utf8(self):
        import tempfile

        with tempfile.NamedTemporaryFile() as fh:
            fh.write("hello pocket".encode())
            fh.flush()
            self.assertEqual(search_service.extract_text(fh.name, "note.txt", "text/plain"), "hello pocket")


class TestSearchEndpoint(unittest.TestCase):
    def setUp(self):
        self.engine = get_test_engine()
        self.session = get_test_session(self.engine)
        self.user = User(login="owner@example.test", name="Owner")
        self.session.add(self.user)
        self.session.commit()
        self.session.refresh(self.user)

        def override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.session.close()

    def test_search_with_no_index_returns_empty(self):
        # No chunks and no vec table exist in the in-memory DB; search should short-circuit to [].
        resp = self.client.get("/api/search?q=anything")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_suggest_with_no_matches(self):
        resp = self.client.get("/api/search/suggest?q=zzz")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["folders"], [])
        self.assertEqual(body["files"], [])


if __name__ == "__main__":
    unittest.main()
