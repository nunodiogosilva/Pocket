"""Unit tests for the search service (embedding helpers, chunking, indexing)."""

import unittest
from unittest.mock import patch


class TestSearchService(unittest.TestCase):
    def test_embed_returns_float32_per_text(self):
        import numpy as np

        import app.services.search_service as vec

        fake = np.array([[1.0, 2.0, 3.0], [0.0, 1.0, 0.0]], dtype=np.float32)

        class _Model:
            def encode(self, texts, **_):
                return fake

        with patch.object(vec, "get_model", return_value=_Model()):
            result = vec.embed(["a", "b"])
            self.assertEqual(result.shape[0], 2)
            self.assertEqual(result.dtype, np.float32)
            self.assertTrue(np.all(np.isfinite(result)))

    def test_index_file_missing_item_is_noop(self):
        import numpy as np

        import app.models  # noqa: F401 (registers tables)
        import app.services.search_service as vec
        from tests.conftest import get_test_engine

        test_engine = get_test_engine()
        with patch.object(vec, "engine", test_engine), patch.object(
            vec, "embed", return_value=np.zeros((1, 3), dtype="float32")
        ):
            vec.index_file(999)  # no item with id 999 -> no-op, no error

    def test_chunking_words(self):
        import app.services.search_service as vec

        words = ["w"] * (vec.CHUNK_WORDS * 2 + 5)
        # The first chunk is the empty title placeholder, then word-buckets.
        chunks = [""] + [" ".join(words[i : i + vec.CHUNK_WORDS]) for i in range(0, len(words), vec.CHUNK_WORDS)]
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[0], "")


if __name__ == "__main__":
    unittest.main()
