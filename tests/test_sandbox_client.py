import os
import unittest
from unittest.mock import patch

from app.sandbox_client import (
    DockerSandboxProvider,
    ProxmoxSandboxProvider,
    SandboxResult,
    get_sandbox_provider,
)


class TestDockerSandboxProvider(unittest.TestCase):
    def test_run_posts_to_the_configured_url_and_returns_result(self):
        captured = {}

        def fake_post_json(url, payload, *, timeout):
            captured["url"] = url
            captured["payload"] = payload
            captured["timeout"] = timeout
            return {"stdout": "2\n", "stderr": "", "exit_code": 0, "timed_out": False}

        with patch("app.sandbox_client._post_json", side_effect=fake_post_json):
            provider = DockerSandboxProvider(base_url="http://sandbox-runner:8090")
            result = provider.run("print(1+1)", timeout_s=5)

        self.assertEqual(captured["url"], "http://sandbox-runner:8090/run")
        self.assertEqual(captured["payload"], {"code": "print(1+1)", "language": "python", "timeout_s": 5})
        self.assertGreater(captured["timeout"], 5)  # HTTP timeout must exceed the runner's own execution ceiling
        self.assertIsInstance(result, SandboxResult)
        self.assertEqual(result.stdout, "2\n")
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.timed_out)

    def test_run_reports_timeout_from_the_runner(self):
        with patch("app.sandbox_client._post_json",
                    return_value={"stdout": "", "stderr": "", "exit_code": 124, "timed_out": True}):
            result = DockerSandboxProvider().run("while True: pass", timeout_s=2)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.exit_code, 124)

    def test_run_returns_a_result_instead_of_raising_when_the_runner_is_unreachable(self):
        with patch("app.sandbox_client._post_json", side_effect=OSError("connection refused")):
            result = DockerSandboxProvider().run("print(1)")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("sandbox_unreachable", result.stderr)

    def test_base_url_defaults_to_env_var_then_the_compose_dns_name(self):
        with patch.dict(os.environ, {"HIVE_SANDBOX_URL": "http://custom-host:9999"}, clear=False):
            self.assertEqual(DockerSandboxProvider().base_url, "http://custom-host:9999")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(DockerSandboxProvider().base_url, "http://sandbox-runner:8090")


class TestProxmoxSandboxProvider(unittest.TestCase):
    def test_run_raises_not_implemented_rather_than_guessing(self):
        with self.assertRaises(NotImplementedError):
            ProxmoxSandboxProvider().run("print(1)")


class TestGetSandboxProvider(unittest.TestCase):
    def test_defaults_to_docker(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(get_sandbox_provider(), DockerSandboxProvider)

    def test_selects_docker_explicitly(self):
        with patch.dict(os.environ, {"HIVE_SANDBOX_PROVIDER": "docker"}, clear=False):
            self.assertIsInstance(get_sandbox_provider(), DockerSandboxProvider)

    def test_selects_proxmox(self):
        with patch.dict(os.environ, {"HIVE_SANDBOX_PROVIDER": "proxmox"}, clear=False):
            self.assertIsInstance(get_sandbox_provider(), ProxmoxSandboxProvider)

    def test_is_case_insensitive(self):
        with patch.dict(os.environ, {"HIVE_SANDBOX_PROVIDER": "PROXMOX"}, clear=False):
            self.assertIsInstance(get_sandbox_provider(), ProxmoxSandboxProvider)


if __name__ == "__main__":
    unittest.main()
