import json
import os
import unittest
from unittest.mock import patch

from app.generation_client import generate_json, generation_config, get_generation_health


class TestGenerationClient(unittest.TestCase):
    def test_generation_config_uses_env(self):
        env = {
            "HIVE_OLLAMA_URL": "http://ollama.local:11434/",
            "HIVE_GENERATION_MODEL": "chat-test",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = generation_config()
        self.assertEqual(cfg["url"], "http://ollama.local:11434")
        self.assertEqual(cfg["model"], "chat-test")

    def test_generation_health_reports_missing_model(self):
        with patch("app.generation_client._get_json", return_value={"models": [{"name": "qwen3:4b"}]}):
            health = get_generation_health()
        self.assertEqual(health["status"], "missing_model")
        self.assertFalse(health["model_ready"])

    def test_generation_health_accepts_tagged_model_names(self):
        env = {"HIVE_GENERATION_MODEL": "llama3.1"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.generation_client._get_json", return_value={"models": [{"name": "llama3.1:8b"}]}):
                health = get_generation_health()
        self.assertEqual(health["status"], "ready")
        self.assertTrue(health["model_ready"])

    def test_generation_health_unavailable_on_network_error(self):
        with patch("app.generation_client._get_json", side_effect=OSError("refused")):
            health = get_generation_health()
        self.assertEqual(health["status"], "unavailable")

    def test_generate_json_parses_message_content(self):
        response = {"message": {"content": json.dumps({"blocks": [{"block_type": "text"}]})}}
        with patch("app.generation_client._post_json", return_value=response):
            result = generate_json("system", "user")
        self.assertEqual(result["blocks"][0]["block_type"], "text")

    def test_generate_json_raises_on_empty_content(self):
        with patch("app.generation_client._post_json", return_value={"message": {"content": ""}}):
            with self.assertRaises(RuntimeError):
                generate_json("system", "user")

    def test_generate_json_raises_on_invalid_json(self):
        with patch("app.generation_client._post_json", return_value={"message": {"content": "not json"}}):
            with self.assertRaises(RuntimeError):
                generate_json("system", "user")

    def test_generate_json_raises_on_network_failure(self):
        with patch("app.generation_client._post_json", side_effect=OSError("refused")):
            with self.assertRaises(RuntimeError):
                generate_json("system", "user")


if __name__ == "__main__":
    unittest.main()
