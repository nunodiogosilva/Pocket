import os
import sys
import unittest

# Ensure API root is in sys.path
API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from models import FileMeta, FileShare, User
from services import storage
from tests.conftest import get_test_engine, get_test_session


class TestStorageService(unittest.TestCase):
    def setUp(self):
        self.engine = get_test_engine()
        self.session = get_test_session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_file_access_control_isolated_by_owner(self):
        """Files owned by user A are inaccessible to user B without explicit share."""
        user_a = User(login="user_a@ts.net", name="User A")
        user_b = User(login="user_b@ts.net", name="User B")
        self.session.add_all([user_a, user_b])
        self.session.commit()

        file_a = FileMeta(
            filename="confidential.txt",
            storage_path="/tmp/fake_confidential.txt",
            file_size=1024,
            mime_type="text/plain",
            owner_id=user_a.id,
        )
        self.session.add(file_a)
        self.session.commit()

        # User A can access
        accessible_a = storage.get_accessible_file(self.session, user_a, file_a.id)
        self.assertIsNotNone(accessible_a)

        # User B cannot access
        accessible_b = storage.get_accessible_file(self.session, user_b, file_a.id)
        self.assertIsNone(accessible_b)

    def test_file_access_control_allows_explicit_share(self):
        """Explicit collaboration linkages (FileShare) grant access."""
        user_a = User(login="alice@ts.net", name="Alice")
        user_b = User(login="bob@ts.net", name="Bob")
        self.session.add_all([user_a, user_b])
        self.session.commit()

        shared_file = FileMeta(
            filename="team_notes.md",
            storage_path="/tmp/fake_notes.md",
            file_size=2048,
            mime_type="text/markdown",
            owner_id=user_a.id,
        )
        self.session.add(shared_file)
        self.session.commit()

        # Share with user B by login
        share = FileShare(
            file_id=shared_file.id,
            shared_with_user_id=user_b.id,
            shared_with_login=user_b.login,
            permission="read",
        )
        self.session.add(share)
        self.session.commit()

        # User B can now access
        accessible_b = storage.get_accessible_file(self.session, user_b, shared_file.id)
        self.assertIsNotNone(accessible_b)
        self.assertEqual(accessible_b.filename, "team_notes.md")

    def test_create_and_nest_folders(self):
        """Folder Support: Explicit folder creation and parent-child hierarchy."""
        user = User(login="alice@ts.net", name="Alice")
        self.session.add(user)
        self.session.commit()

        root_folder = storage.create_folder(self.session, user, "Projects", parent_id=None)
        self.assertTrue(root_folder.is_folder)
        self.assertEqual(root_folder.filename, "Projects")

        sub_folder = storage.create_folder(self.session, user, "API", parent_id=root_folder.id)
        self.assertTrue(sub_folder.is_folder)
        self.assertEqual(sub_folder.parent_id, root_folder.id)

    def test_resolve_folder_path_hierarchy(self):
        """Folder Support: Automatic intermediate folder creation for folder uploads."""
        user = User(login="alice@ts.net", name="Alice")
        self.session.add(user)
        self.session.commit()

        innermost_id = storage.resolve_or_create_folder_path(
            self.session, user, "MyProject/docs/api", base_parent_id=None
        )
        self.assertIsNotNone(innermost_id)

        # Check that 'MyProject', 'docs', and 'api' were created
        api_folder = self.session.get(FileMeta, innermost_id)
        self.assertEqual(api_folder.filename, "api")
        self.assertTrue(api_folder.is_folder)

        docs_folder = self.session.get(FileMeta, api_folder.parent_id)
        self.assertEqual(docs_folder.filename, "docs")

        project_folder = self.session.get(FileMeta, docs_folder.parent_id)
        self.assertEqual(project_folder.filename, "MyProject")
        self.assertIsNone(project_folder.parent_id)

    def test_recursive_folder_deletion(self):
        """Folder Support: Deleting a folder recursively deletes all children without foreign key errors."""
        user = User(login="alice@ts.net", name="Alice")
        self.session.add(user)
        self.session.commit()

        folder = storage.create_folder(self.session, user, "ParentFolder", None)
        sub = storage.create_folder(self.session, user, "ChildFolder", folder.id)
        file_item = FileMeta(
            filename="child_file.txt",
            storage_path="",
            file_size=10,
            mime_type="text/plain",
            parent_id=sub.id,
            owner_id=user.id,
        )
        self.session.add(file_item)
        self.session.commit()

        # Delete root folder
        success = storage.delete_file(self.session, user, folder.id)
        self.assertTrue(success)

        # All records should be deleted
        self.assertIsNone(self.session.get(FileMeta, folder.id))
        self.assertIsNone(self.session.get(FileMeta, sub.id))
        self.assertIsNone(self.session.get(FileMeta, file_item.id))

    def test_rename_file_and_folder(self):
        """Users can rename files and folders."""
        user = User(login="alice@ts.net", name="Alice")
        self.session.add(user)
        self.session.commit()

        folder = storage.create_folder(self.session, user, "OldFolderName", None)
        updated_folder = storage.rename_item(self.session, user, folder.id, "NewFolderName", is_folder=True)
        self.assertEqual(updated_folder.filename, "NewFolderName")

        file_item = FileMeta(
            filename="old.txt",
            storage_path="",
            file_size=10,
            mime_type="text/plain",
            parent_id=folder.id,
            owner_id=user.id,
        )
        self.session.add(file_item)
        self.session.commit()

        updated_file = storage.rename_item(self.session, user, file_item.id, "new.txt", is_folder=False)
        self.assertEqual(updated_file.filename, "new.txt")

    def test_recycle_bin_soft_delete_and_restore(self):
        """Soft delete moves items to bin, with manual restore."""
        user = User(login="alice@ts.net", name="Alice")
        self.session.add(user)
        self.session.commit()

        folder = storage.create_folder(self.session, user, "Work", None)
        file_item = FileMeta(
            filename="doc.pdf",
            storage_path="",
            file_size=500,
            mime_type="application/pdf",
            parent_id=folder.id,
            owner_id=user.id,
        )
        self.session.add(file_item)
        self.session.commit()

        # Soft delete folder
        self.assertTrue(storage.soft_delete(self.session, user, folder.id))

        # Check not in active directory listing
        active = storage.list_directory(self.session, user, None)
        self.assertEqual(len(active.folders), 0)

        # Check in bin
        bin_items = storage.list_bin(self.session, user)
        self.assertEqual(len(bin_items), 1)
        self.assertEqual(bin_items[0].filename, "Work")
        self.assertEqual(bin_items[0].days_left, 30)

        # Restore from bin
        self.assertTrue(storage.restore_from_bin(self.session, user, folder.id))
        active_restored = storage.list_directory(self.session, user, None)
        self.assertEqual(len(active_restored.folders), 1)
        self.assertEqual(len(storage.list_bin(self.session, user)), 0)

    def test_user_storage_usage(self):
        """Storage usage reflects active (non-deleted) files."""
        user = User(login="alice@ts.net", name="Alice")
        self.session.add(user)
        self.session.commit()

        f1 = FileMeta(
            filename="f1.dat",
            storage_path="",
            file_size=1024,
            mime_type="application/octet-stream",
            owner_id=user.id,
        )
        f2 = FileMeta(
            filename="f2.dat",
            storage_path="",
            file_size=2048,
            mime_type="application/octet-stream",
            owner_id=user.id,
        )
        self.session.add_all([f1, f2])
        self.session.commit()

        stats = storage.get_user_storage(self.session, user)
        self.assertEqual(stats["used_bytes"], 3072)
        self.assertEqual(stats["file_count"], 2)

        # Soft deleting f1 should decrease active storage
        storage.soft_delete(self.session, user, f1.id)
        stats_after = storage.get_user_storage(self.session, user)
        self.assertEqual(stats_after["used_bytes"], 2048)
        self.assertEqual(stats_after["file_count"], 1)


if __name__ == "__main__":
    unittest.main()
