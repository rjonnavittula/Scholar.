import os
import unittest
from unittest.mock import patch

from app.vector_store import get_memory_layers, qdrant_config


class TestVectorStore(unittest.TestCase):
    def test_qdrant_config_uses_env_with_defaults(self):
        env = {
            "HIVE_QDRANT_URL": "http://qdrant.local:6333",
            "HIVE_QDRANT_COLLECTION": "scholar_test",
            "HIVE_QDRANT_VECTOR_SIZE": "1024",
            "HIVE_EMBEDDING_MODEL": "test-embed",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = qdrant_config()

        self.assertEqual(cfg["url"], "http://qdrant.local:6333")
        self.assertEqual(cfg["collection"], "scholar_test")
        self.assertEqual(cfg["vector_size"], 1024)
        self.assertEqual(cfg["embedding_model"], "test-embed")

    def test_memory_layers_keep_okf_visible(self):
        with patch("app.vector_store.get_qdrant_health", return_value={
            "layer": "qdrant",
            "status": "missing_collection",
            "collection": "hive_scholar_chunks",
            "embedding_model": "nomic-embed-text",
        }):
            layers = get_memory_layers()

        ids = [layer["id"] for layer in layers["layers"]]
        self.assertEqual(layers["phase"], "D")
        self.assertIn("sql", ids)
        self.assertIn("qdrant", ids)
        self.assertIn("rag", ids)
        self.assertIn("okf", ids)
        okf = next(layer for layer in layers["layers"] if layer["id"] == "okf")
        self.assertEqual(okf["status"], "planned")


if __name__ == "__main__":
    unittest.main()
