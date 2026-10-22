"""Tests for the item (file/folder) endpoints and the item service layer."""

import unittest

from fastapi.testclient import TestClient

from app.dependencies.db import get_db
from app.dependencies.tailscale import get_current_user
from app.main import app
from app.models.item import Item
from app.models.user import User
from app.services import item_service
from tests.conftest import get_test_engine, get_test_session


class _Base(unittest.TestCase):
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

    def _folder(self, name="docs", parent_id=None):
        f = Item(filename=name, storage_path="", file_size=0, mime_type="inode/directory",
                 parent_id=parent_id, is_folder=True, owner_id=self.user.id)
        self.session.add(f)
        self.session.commit()
        self.session.refresh(f)
        return f


class TestItemEndpoints(_Base):
    def test_list_files_returns_only_files(self):
        self._folder()
        file_item = Item(filename="note.txt", storage_path="/tmp/note.txt", file_size=4,
                         mime_type="text/plain", is_folder=False, owner_id=self.user.id)
        self.session.add(file_item)
        self.session.commit()

        resp = self.client.get("/api/items?type=file")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([i["filename"] for i in resp.json()], ["note.txt"])

    def test_create_folder_endpoint(self):
        # The endpoint schedules vector indexing as a background task; TestClient
        # runs it synchronously, so patch it to a no-op (we're testing HTTP, not indexing).
        from unittest.mock import patch

        from app.services import search_service

        with patch.object(search_service, "index_file", lambda _id: None):
            resp = self.client.post("/api/items", json={"name": "Projects", "parent_id": None})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_folder"])

    def test_directory_contents_separates_folders_and_files(self):
        folder = self._folder("work")
        file_item = Item(filename="a.txt", storage_path="/tmp/a.txt", file_size=1,
                         mime_type="text/plain", is_folder=False, owner_id=self.user.id)
        self.session.add(file_item)
        self.session.commit()

        resp = self.client.get(f"/api/items/directory?parent_id={folder.id}")
        self.assertEqual(resp.status_code, 200)

    def test_unknown_ids_return_404(self):
        self.assertEqual(self.client.get("/api/items/99999").status_code, 404)

    def test_storage_usage_endpoint(self):
        resp = self.client.get("/api/items/storage")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("used_bytes", resp.json())


class TestItemService(_Base):
    def test_create_and_rename_folder(self):
        folder = item_service.create_folder(self.session, self.user, "Reports", None)
        self.assertTrue(folder.is_folder)
        renamed = item_service.rename_item(self.session, self.user, folder.id, "Annual Reports", is_folder=True)
        self.assertEqual(renamed.filename, "Annual Reports")

    def test_rename_collision_raises(self):
        a = item_service.create_folder(self.session, self.user, "A", None)
        item_service.create_folder(self.session, self.user, "B", None)
        with self.assertRaises(ValueError):
            item_service.rename_item(self.session, self.user, a.id, "B", is_folder=True)

    def test_move_into_descendant_rejected(self):
        parent = item_service.create_folder(self.session, self.user, "parent", None)
        child = item_service.create_folder(self.session, self.user, "child", parent.id)
        with self.assertRaises(ValueError):
            item_service.move_item(self.session, self.user, parent.id, child.id)

    def test_soft_delete_then_restore(self):
        f = self._folder("trashme")
        self.assertTrue(item_service.soft_delete(self.session, self.user, f.id))
        self.assertTrue(self.session.get(Item, f.id).is_deleted)
        self.assertTrue(item_service.restore_from_bin(self.session, self.user, f.id))
        self.assertFalse(self.session.get(Item, f.id).is_deleted)

    def test_bin_listing_and_empty(self):
        f = self._folder("deleteme")
        item_service.soft_delete(self.session, self.user, f.id)
        bin_items = item_service.list_bin(self.session, self.user)
        self.assertEqual(len(bin_items), 1)
        self.assertTrue(bin_items[0].days_left >= 0)


if __name__ == "__main__":
    unittest.main()
