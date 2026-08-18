import os
import unittest
from unittest.mock import MagicMock, patch

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
        self.assertEqual(captured["payload"], {
            "code": "print(1+1)", "language": "python", "timeout_s": 5,
            "capture_media": False, "capture_video": False, "scene_name": "",
        })
        self.assertGreater(captured["timeout"], 5)  # HTTP timeout must exceed the runner's own execution ceiling
        self.assertIsInstance(result, SandboxResult)
        self.assertEqual(result.stdout, "2\n")
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.timed_out)
        self.assertIsNone(result.media_kind)
        self.assertIsNone(result.media_base64)

    def test_run_passes_capture_media_through_and_returns_media_fields(self):
        captured = {}

        def fake_post_json(url, payload, *, timeout):
            captured["payload"] = payload
            return {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False,
                     "media_kind": "image/png", "media_base64": "Zm9v"}

        with patch("app.sandbox_client._post_json", side_effect=fake_post_json):
            result = DockerSandboxProvider().run("plt.savefig('/tmp/output.png')", capture_media=True)

        self.assertTrue(captured["payload"]["capture_media"])
        self.assertEqual(result.media_kind, "image/png")
        self.assertEqual(result.media_base64, "Zm9v")

    def test_run_passes_capture_video_and_scene_name_through(self):
        captured = {}

        def fake_post_json(url, payload, *, timeout):
            captured["payload"] = payload
            return {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False,
                     "media_kind": "video/mp4", "media_base64": "Zm9v"}

        with patch("app.sandbox_client._post_json", side_effect=fake_post_json):
            result = DockerSandboxProvider().run(
                "class MyScene(Scene): pass", timeout_s=60, capture_video=True, scene_name="MyScene",
            )

        self.assertTrue(captured["payload"]["capture_video"])
        self.assertEqual(captured["payload"]["scene_name"], "MyScene")
        self.assertEqual(result.media_kind, "video/mp4")

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
    def _cfg(self):
        return MagicMock(template_vmid=9000, plot_template_vmid=9001, visual_template_vmid=9002)

    def test_run_reports_a_clear_error_when_not_configured(self):
        with patch("app.proxmox_client.load_config",
                    side_effect=ValueError("proxmox_not_configured: missing HIVE_PROXMOX_HOST")):
            result = ProxmoxSandboxProvider().run("print(1)")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("proxmox_not_configured", result.stderr)

    def test_run_requires_scene_name_for_capture_video(self):
        result = ProxmoxSandboxProvider().run("manim code", capture_video=True)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("scene_name", result.stderr)

    def test_run_clones_execs_and_destroys_on_success(self):
        cfg = self._cfg()
        ssh = MagicMock()
        with patch("app.proxmox_client.load_config", return_value=cfg), \
             patch("app.proxmox_client.api_client", return_value="API") as mock_api_client, \
             patch("app.proxmox_client.clone_template", return_value=9100) as mock_clone, \
             patch("app.proxmox_client.start_container") as mock_start, \
             patch("app.proxmox_client.ssh_client", return_value=ssh), \
             patch("app.proxmox_client.pct_exec", return_value=("hi\n", "", 0, False)) as mock_exec, \
             patch("app.proxmox_client.destroy_container") as mock_destroy:
            result = ProxmoxSandboxProvider().run("print('hi')", timeout_s=5)

        mock_api_client.assert_called_once_with(cfg)
        mock_clone.assert_called_once_with("API", cfg, cfg.template_vmid)
        mock_start.assert_called_once_with("API", cfg, 9100)
        mock_exec.assert_called_once_with(ssh, 9100, "print('hi')", 5)
        mock_destroy.assert_called_once_with("API", cfg, 9100)
        ssh.close.assert_called_once()
        self.assertEqual(result.stdout, "hi\n")
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.media_kind)

    def test_run_always_destroys_the_clone_even_if_exec_raises(self):
        cfg = self._cfg()
        with patch("app.proxmox_client.load_config", return_value=cfg), \
             patch("app.proxmox_client.api_client", return_value="API"), \
             patch("app.proxmox_client.clone_template", return_value=9100), \
             patch("app.proxmox_client.start_container"), \
             patch("app.proxmox_client.ssh_client", return_value=MagicMock()), \
             patch("app.proxmox_client.pct_exec", side_effect=RuntimeError("ssh broke")), \
             patch("app.proxmox_client.destroy_container") as mock_destroy:
            result = ProxmoxSandboxProvider().run("print(1)")

        mock_destroy.assert_called_once_with("API", cfg, 9100)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("proxmox_exec_failed", result.stderr)

    def test_run_always_destroys_the_clone_even_if_provisioning_of_the_clone_itself_fails_after_creation(self):
        # clone_template succeeds (we have a vmid) but start_container blows up -
        # destroy must still run so nothing is left behind.
        cfg = self._cfg()
        with patch("app.proxmox_client.load_config", return_value=cfg), \
             patch("app.proxmox_client.api_client", return_value="API"), \
             patch("app.proxmox_client.clone_template", return_value=9100), \
             patch("app.proxmox_client.start_container", side_effect=RuntimeError("start failed")), \
             patch("app.proxmox_client.destroy_container") as mock_destroy:
            result = ProxmoxSandboxProvider().run("print(1)")

        mock_destroy.assert_called_once_with("API", cfg, 9100)
        self.assertEqual(result.exit_code, 1)

    def test_run_does_not_attempt_cleanup_when_cloning_itself_fails(self):
        # no vmid was ever created, so there is nothing to destroy() - and
        # destroy_container isn't even importable-safe to call without one.
        cfg = self._cfg()
        with patch("app.proxmox_client.load_config", return_value=cfg), \
             patch("app.proxmox_client.api_client", return_value="API"), \
             patch("app.proxmox_client.clone_template", side_effect=RuntimeError("no next id")), \
             patch("app.proxmox_client.destroy_container") as mock_destroy:
            result = ProxmoxSandboxProvider().run("print(1)")

        mock_destroy.assert_not_called()
        self.assertEqual(result.exit_code, 1)
        self.assertIn("proxmox_provision_failed", result.stderr)

    def test_run_uses_the_plot_template_and_pulls_output_png_when_capture_media(self):
        cfg = self._cfg()
        with patch("app.proxmox_client.load_config", return_value=cfg), \
             patch("app.proxmox_client.api_client", return_value="API"), \
             patch("app.proxmox_client.clone_template", return_value=9100) as mock_clone, \
             patch("app.proxmox_client.start_container"), \
             patch("app.proxmox_client.ssh_client", return_value=MagicMock()), \
             patch("app.proxmox_client.pct_exec", return_value=("", "", 0, False)), \
             patch("app.proxmox_client.pull_file", return_value=b"pngbytes") as mock_pull, \
             patch("app.proxmox_client.destroy_container"):
            result = ProxmoxSandboxProvider().run("plt.savefig(...)", capture_media=True)

        mock_clone.assert_called_once_with("API", cfg, cfg.plot_template_vmid)
        mock_pull.assert_called_once()
        self.assertEqual(mock_pull.call_args.args[2], "/tmp/output.png")
        self.assertEqual(result.media_kind, "image/png")
        self.assertTrue(result.media_base64)

    def test_run_uses_the_visual_template_and_finds_the_mp4_when_capture_video(self):
        cfg = self._cfg()
        with patch("app.proxmox_client.load_config", return_value=cfg), \
             patch("app.proxmox_client.api_client", return_value="API"), \
             patch("app.proxmox_client.clone_template", return_value=9100) as mock_clone, \
             patch("app.proxmox_client.start_container"), \
             patch("app.proxmox_client.ssh_client", return_value=MagicMock()), \
             patch("app.proxmox_client.pct_exec", return_value=("", "", 0, False)), \
             patch("app.proxmox_client.find_first_file", return_value="/tmp/media/x.mp4") as mock_find, \
             patch("app.proxmox_client.pull_file", return_value=b"mp4bytes") as mock_pull, \
             patch("app.proxmox_client.destroy_container"):
            result = ProxmoxSandboxProvider().run("manim code", capture_video=True, scene_name="MyScene")

        mock_clone.assert_called_once_with("API", cfg, cfg.visual_template_vmid)
        mock_find.assert_called_once()
        mock_pull.assert_called_once_with(mock_pull.call_args.args[0], 9100, "/tmp/media/x.mp4")
        self.assertEqual(result.media_kind, "video/mp4")

    def test_run_never_pulls_media_when_the_exec_itself_failed(self):
        cfg = self._cfg()
        with patch("app.proxmox_client.load_config", return_value=cfg), \
             patch("app.proxmox_client.api_client", return_value="API"), \
             patch("app.proxmox_client.clone_template", return_value=9100), \
             patch("app.proxmox_client.start_container"), \
             patch("app.proxmox_client.ssh_client", return_value=MagicMock()), \
             patch("app.proxmox_client.pct_exec", return_value=("", "boom", 1, False)), \
             patch("app.proxmox_client.pull_file") as mock_pull, \
             patch("app.proxmox_client.destroy_container"):
            result = ProxmoxSandboxProvider().run("plt.savefig(...)", capture_media=True)

        mock_pull.assert_not_called()
        self.assertEqual(result.exit_code, 1)
        self.assertIsNone(result.media_kind)


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
