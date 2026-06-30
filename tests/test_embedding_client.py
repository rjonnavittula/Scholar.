import os
import unittest
from unittest.mock import patch

from app.embedding_client import (
    embedding_config,
    embed_text_preview,
    get_embedding_health,
    normalize_embedding_response,
)


class TestEmbeddingClient(unittest.TestCase):
    def test_embedding_config_uses_env(self):
        env = {
            "HIVE_OLLAMA_URL": "http://ollama.local:11434/",
            "HIVE_EMBEDDING_MODEL": "embed-test",
            "HIVE_EMBEDDING_DIM": "3",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = embedding_config()
        self.assertEqual(cfg["url"], "http://ollama.local:11434")
        self.assertEqual(cfg["model"], "embed-test")
        self.assertEqual(cfg["expected_dim"], 3)

    def test_normalize_embedding_response_supports_legacy_endpoint(self):
        self.assertEqual(normalize_embedding_response({"embedding": [1, 2, 3]}), [1.0, 2.0, 3.0])

    def test_normalize_embedding_response_supports_embed_endpoint(self):
        self.assertEqual(normalize_embedding_response({"embeddings": [[0.1, 0.2]]}), [0.1, 0.2])

    def test_embedding_health_reports_missing_model(self):
        with patch("app.embedding_client._get_json", return_value={"models": [{"name": "qwen3:4b"}]}):
            health = get_embedding_health()
        self.assertEqual(health["status"], "missing_model")
        self.assertFalse(health["model_ready"])

    def test_embedding_health_accepts_tagged_model_names(self):
        env = {"HIVE_EMBEDDING_MODEL": "nomic-embed-text"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.embedding_client._get_json", return_value={"models": [{"name": "nomic-embed-text:latest"}]}):
                health = get_embedding_health()
        self.assertEqual(health["status"], "ready")
        self.assertTrue(health["model_ready"])

    def test_embed_text_preview_hides_full_vector(self):
        env = {"HIVE_EMBEDDING_DIM": "3", "HIVE_EMBEDDING_MODEL": "embed-test"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.embedding_client._post_json", return_value={"embedding": [0.1, 0.2, 0.3]}):
                result = embed_text_preview("hello")
        self.assertEqual(result["dimension"], 3)
        self.assertEqual(result["preview"], [0.1, 0.2, 0.3])
        self.assertIn("vector_checksum", result)


if __name__ == "__main__":
    unittest.main()
