import os
import unittest
from unittest.mock import MagicMock, patch

from app.vector_store import get_memory_layers, qdrant_config, search_chunks, upsert_source_chunks


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

    def test_memory_layers_okf_ready(self):
        with patch("app.vector_store.get_qdrant_health", return_value={
            "layer": "qdrant",
            "status": "missing_collection",
            "collection": "hive_scholar_chunks",
            "embedding_model": "nomic-embed-text",
        }), patch("app.embedding_client.get_embedding_health", return_value={
            "layer": "embeddings", "status": "unavailable",
        }), patch("app.generation_client.get_generation_health", return_value={
            "layer": "generation", "status": "unavailable",
        }):
            layers = get_memory_layers()

        ids = [layer["id"] for layer in layers["layers"]]
        self.assertEqual(layers["phase"], "E")
        self.assertIn("sql", ids)
        self.assertIn("qdrant", ids)
        self.assertIn("rag", ids)
        self.assertIn("okf", ids)
        okf = next(layer for layer in layers["layers"] if layer["id"] == "okf")
        self.assertEqual(okf["status"], "ready")

    def test_memory_layers_rag_ready_only_when_all_layers_ready(self):
        ready = {"status": "ready"}
        with patch("app.vector_store.get_qdrant_health", return_value=ready), \
             patch("app.embedding_client.get_embedding_health", return_value=ready), \
             patch("app.generation_client.get_generation_health", return_value=ready):
            layers = get_memory_layers()
        rag = next(layer for layer in layers["layers"] if layer["id"] == "rag")
        self.assertEqual(rag["status"], "ready")

    def test_upsert_source_chunks_returns_zero_counts_for_empty_source(self):
        with patch("app.chunk_store.list_source_chunks", return_value=[]):
            result = upsert_source_chunks(MagicMock(), 1)
        self.assertEqual(result, {"status": "ready", "indexed": 0, "skipped": 0, "failed": 0})

    def test_upsert_source_chunks_reports_source_not_found(self):
        with patch("app.chunk_store.list_source_chunks", return_value=None):
            with self.assertRaises(ValueError):
                upsert_source_chunks(MagicMock(), 999)

    def test_upsert_source_chunks_embeds_new_and_skips_unchanged(self):
        chunks = [
            {"id": 1, "source_id": 1, "heading": "A", "heading_path": [], "position": 1, "chunk_hash": "hash1", "body_text": "alpha"},
            {"id": 2, "source_id": 1, "heading": "B", "heading_path": [], "position": 2, "chunk_hash": "hash2", "body_text": "beta"},
        ]
        existing_record = MagicMock(id=1, payload={"chunk_hash": "hash1"})
        mock_client = MagicMock()
        mock_client.retrieve.return_value = [existing_record]

        with patch("app.chunk_store.list_source_chunks", return_value=chunks), \
             patch("app.vector_store._client", return_value=mock_client), \
             patch("app.vector_store.ensure_scholar_collection", return_value={"status": "ready"}), \
             patch("app.embedding_client.embed_text", return_value=[0.1, 0.2]):
            result = upsert_source_chunks(MagicMock(), 1)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["indexed"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 0)
        mock_client.upsert.assert_called_once()

    def test_upsert_source_chunks_unavailable_when_qdrant_unreachable(self):
        chunks = [{"id": 1, "source_id": 1, "heading": "A", "heading_path": [], "position": 1, "chunk_hash": "hash1", "body_text": "alpha"}]
        with patch("app.chunk_store.list_source_chunks", return_value=chunks), \
             patch("app.vector_store._client", side_effect=RuntimeError("no qdrant")):
            result = upsert_source_chunks(MagicMock(), 1)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["failed"], 1)

    def test_search_chunks_returns_empty_without_source_ids(self):
        self.assertEqual(search_chunks("query", []), [])

    def test_search_chunks_returns_empty_on_failure(self):
        with patch("app.embedding_client.embed_text", side_effect=RuntimeError("down")):
            self.assertEqual(search_chunks("query", [1, 2]), [])

    def test_search_chunks_maps_query_points_response(self):
        # qdrant-client >=1.10 exposes query_points() (returning a .points list),
        # not the old search() method — this pins that contract.
        point = MagicMock(id=99, score=0.87, payload={"chunk_id": 7, "source_id": 1})
        mock_response = MagicMock(points=[point])
        mock_client = MagicMock()
        mock_client.query_points.return_value = mock_response

        with patch("app.vector_store._client", return_value=mock_client), \
             patch("app.embedding_client.embed_text", return_value=[0.1, 0.2]):
            results = search_chunks("query", [1])

        mock_client.query_points.assert_called_once()
        self.assertEqual(results, [{"chunk_id": 7, "source_id": 1, "score": 0.87}])


if __name__ == "__main__":
    unittest.main()
