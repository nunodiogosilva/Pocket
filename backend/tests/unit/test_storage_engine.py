"""Unit tests for the low-level streaming storage engine."""

import io
import os
import tempfile
import unittest

from app.core import storage_engine


class TestStorageEngine(unittest.TestCase):
    def test_stream_to_disk_writes_all_bytes(self):
        payload = os.urandom(3 * 1024 * 1024)  # 3 MiB
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "out.bin")
            source = io.BytesIO(payload)
            size = storage_engine.stream_to_disk(source, dest)
            self.assertEqual(size, len(payload))
            with open(dest, "rb") as fh:
                self.assertEqual(fh.read(), payload)

    def test_allocate_storage_path_is_unique(self):
        a = storage_engine.allocate_storage_path(1)
        b = storage_engine.allocate_storage_path(1)
        self.assertNotEqual(a, b)
        self.assertTrue(os.path.isdir(os.path.dirname(a)))

    def test_create_folder_zip_contains_entries(self):
        import app.config as cfg

        with tempfile.TemporaryDirectory() as tmp:
            # Point the engine's storage root at an isolated location for this test.
            original = cfg.settings.storage_dir
            cfg.settings.storage_dir = tmp
            os.makedirs(cfg.settings.upload_tmp_dir, exist_ok=True)
            try:
                real = os.path.join(tmp, "real.txt")
                with open(real, "w") as fh:
                    fh.write("content")
                entries = [("Top/a.txt", real), ("Top/emptydir/", None)]
                zip_path = storage_engine.create_folder_zip(entries, "Top")
                self.assertTrue(os.path.exists(zip_path))
                storage_engine.remove_path(zip_path)
                self.assertFalse(os.path.exists(zip_path))
            finally:
                cfg.settings.storage_dir = original


if __name__ == "__main__":
    unittest.main()
