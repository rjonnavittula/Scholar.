import json
import os
import unittest
from unittest.mock import patch

from app.generation_client import generate_json, generate_text, generation_config, get_generation_health, stream_chat


class _FakeStreamResponse:
    """Mimics the file-like object urllib.request.urlopen() returns, line by line."""

    def __init__(self, lines):
        self._lines = [(json.dumps(line) if not isinstance(line, str) else line).encode("utf-8") + b"\n" for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self._lines)


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

    def test_generate_text_returns_content(self):
        with patch("app.generation_client._post_json", return_value={"message": {"content": "a plain reply"}}):
            self.assertEqual(generate_text("system", "user"), "a plain reply")

    def test_generate_text_raises_on_empty_content(self):
        with patch("app.generation_client._post_json", return_value={"message": {"content": ""}}):
            with self.assertRaises(RuntimeError):
                generate_text("system", "user")

    def test_generate_text_raises_on_network_failure(self):
        with patch("app.generation_client._post_json", side_effect=OSError("refused")):
            with self.assertRaises(RuntimeError):
                generate_text("system", "user")

    def test_stream_chat_yields_parsed_ndjson_lines(self):
        lines = [
            {"message": {"content": "Hel"}, "done": False},
            {"message": {"content": "lo"}, "done": False},
            {"done": True},
        ]
        with patch("urllib.request.urlopen", return_value=_FakeStreamResponse(lines)):
            events = list(stream_chat([{"role": "user", "content": "hi"}]))
        self.assertEqual(events, lines)

    def test_stream_chat_skips_blank_lines(self):
        with patch("urllib.request.urlopen", return_value=_FakeStreamResponse(["", {"done": True}])):
            events = list(stream_chat([{"role": "user", "content": "hi"}]))
        self.assertEqual(events, [{"done": True}])

    def test_stream_chat_yields_error_on_connection_failure(self):
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            events = list(stream_chat([{"role": "user", "content": "hi"}]))
        self.assertEqual(len(events), 1)
        self.assertIn("refused", events[0]["error"])

    def test_stream_chat_includes_tools_in_payload_when_provided(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeStreamResponse([{"done": True}])

        tools = [{"type": "function", "function": {"name": "run_python"}}]
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            list(stream_chat([{"role": "user", "content": "hi"}], tools=tools))
        self.assertEqual(captured["body"]["tools"], tools)
        self.assertTrue(captured["body"]["stream"])

    def test_stream_chat_uses_model_override(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeStreamResponse([{"done": True}])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            list(stream_chat([{"role": "user", "content": "hi"}], model="qwen3:4b"))
        self.assertEqual(captured["body"]["model"], "qwen3:4b")


if __name__ == "__main__":
    unittest.main()
