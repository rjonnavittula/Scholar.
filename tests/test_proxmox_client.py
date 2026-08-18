import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from app import proxmox_client as px


def _full_env(**overrides):
    env = {
        "HIVE_PROXMOX_HOST": "pve.local",
        "HIVE_PROXMOX_NODE": "pve",
        "HIVE_PROXMOX_TOKEN_ID": "root@pam!hive-sandbox",
        "HIVE_PROXMOX_TOKEN_SECRET": "secret123",
        "HIVE_PROXMOX_TEMPLATE_VMID": "9000",
        "HIVE_PROXMOX_STORAGE": "local-lvm",
        "HIVE_PROXMOX_SSH_USER": "root",
        "HIVE_PROXMOX_SSH_KEY_PATH": "/keys/id_rsa",
    }
    env.update(overrides)
    return env


def _cfg(**overrides):
    base = dict(
        host="pve.local", port=8006, node="pve", token_id="root@pam!hive-sandbox",
        token_secret="s3cr3t", verify_ssl=False, storage="local-lvm", clone_full=True,
        template_vmid=9000, plot_template_vmid=9001, visual_template_vmid=9002,
        ssh_host="pve.local", ssh_port=22, ssh_user="root", ssh_key_path="/k",
    )
    base.update(overrides)
    return px.ProxmoxConfig(**base)


class TestLoadConfig(unittest.TestCase):
    def test_raises_with_missing_field_names(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                px.load_config()
        self.assertIn("HIVE_PROXMOX_HOST", str(ctx.exception))
        self.assertIn("HIVE_PROXMOX_TOKEN_ID", str(ctx.exception))
        self.assertIn("HIVE_PROXMOX_SSH_KEY_PATH", str(ctx.exception))

    def test_reads_all_values_with_defaults(self):
        with patch.dict(os.environ, _full_env(), clear=True):
            cfg = px.load_config()
        self.assertEqual(cfg.host, "pve.local")
        self.assertEqual(cfg.port, 8006)
        self.assertEqual(cfg.template_vmid, 9000)
        self.assertEqual(cfg.plot_template_vmid, 9000)  # defaults to base template
        self.assertEqual(cfg.visual_template_vmid, 9000)
        self.assertEqual(cfg.ssh_host, "pve.local")  # defaults to host
        self.assertFalse(cfg.verify_ssl)
        self.assertTrue(cfg.clone_full)

    def test_plot_and_visual_templates_can_be_overridden(self):
        env = _full_env(HIVE_PROXMOX_PLOT_TEMPLATE_VMID="9001", HIVE_PROXMOX_VISUAL_TEMPLATE_VMID="9002")
        with patch.dict(os.environ, env, clear=True):
            cfg = px.load_config()
        self.assertEqual(cfg.plot_template_vmid, 9001)
        self.assertEqual(cfg.visual_template_vmid, 9002)

    def test_ssh_host_can_be_overridden_independently_of_the_api_host(self):
        env = _full_env(HIVE_PROXMOX_SSH_HOST="10.0.0.5")
        with patch.dict(os.environ, env, clear=True):
            cfg = px.load_config()
        self.assertEqual(cfg.host, "pve.local")
        self.assertEqual(cfg.ssh_host, "10.0.0.5")

    def test_clone_full_can_be_disabled_for_linked_clones(self):
        env = _full_env(HIVE_PROXMOX_CLONE_FULL="false")
        with patch.dict(os.environ, env, clear=True):
            cfg = px.load_config()
        self.assertFalse(cfg.clone_full)


class TestApiClient(unittest.TestCase):
    def test_parses_the_token_id_into_user_and_token_name(self):
        cfg = _cfg(token_id="root@pam!hive-sandbox", token_secret="s3cr3t")
        with patch("proxmoxer.ProxmoxAPI") as mock_api:
            px.api_client(cfg)
        mock_api.assert_called_once_with(
            "pve.local", port=8006, user="root@pam", token_name="hive-sandbox",
            token_value="s3cr3t", verify_ssl=False,
        )

    def test_rejects_a_token_id_without_a_bang_separator(self):
        cfg = _cfg(token_id="root@pam")
        with self.assertRaises(ValueError):
            px.api_client(cfg)


class TestTaskAndLifecycle(unittest.TestCase):
    def test_wait_for_task_returns_on_success(self):
        api = MagicMock()
        api.nodes.return_value.tasks.return_value.status.get.return_value = {"status": "stopped", "exitstatus": "OK"}
        px.wait_for_task(api, "pve", "UPID:xxx", timeout_s=5)  # no raise

    def test_wait_for_task_raises_on_failure_status(self):
        api = MagicMock()
        api.nodes.return_value.tasks.return_value.status.get.return_value = {
            "status": "stopped", "exitstatus": "some error",
        }
        with self.assertRaises(RuntimeError):
            px.wait_for_task(api, "pve", "UPID:xxx", timeout_s=5)

    def test_wait_for_task_raises_on_timeout(self):
        api = MagicMock()
        api.nodes.return_value.tasks.return_value.status.get.return_value = {"status": "running"}
        with self.assertRaises(RuntimeError):
            px.wait_for_task(api, "pve", "UPID:xxx", timeout_s=0.05)

    def test_clone_template_uses_next_vmid_and_configured_storage(self):
        api = MagicMock()
        api.cluster.nextid.get.return_value = "9100"
        api.nodes.return_value.lxc.return_value.clone.post.return_value = "UPID:clone"
        api.nodes.return_value.tasks.return_value.status.get.return_value = {"status": "stopped", "exitstatus": "OK"}

        cfg = _cfg()
        new_vmid = px.clone_template(api, cfg, cfg.template_vmid)

        self.assertEqual(new_vmid, 9100)
        api.nodes.return_value.lxc.assert_any_call(cfg.template_vmid)
        api.nodes.return_value.lxc.return_value.clone.post.assert_called_once_with(
            newid=9100, storage="local-lvm", full=1,
        )

    def test_clone_template_requests_a_linked_clone_when_configured(self):
        api = MagicMock()
        api.cluster.nextid.get.return_value = "9100"
        api.nodes.return_value.tasks.return_value.status.get.return_value = {"status": "stopped", "exitstatus": "OK"}

        px.clone_template(api, _cfg(clone_full=False), 9000)

        api.nodes.return_value.lxc.return_value.clone.post.assert_called_once_with(
            newid=9100, storage="local-lvm", full=0,
        )

    def test_destroy_container_never_raises_even_if_both_calls_fail(self):
        api = MagicMock()
        api.nodes.return_value.lxc.return_value.status.stop.post.side_effect = RuntimeError("boom")
        api.nodes.return_value.lxc.return_value.delete.side_effect = RuntimeError("boom2")
        px.destroy_container(api, _cfg(), 9100)  # should not raise

    def test_destroy_container_purges_after_stopping(self):
        api = MagicMock()
        api.nodes.return_value.lxc.return_value.status.stop.post.return_value = "UPID:stop"
        api.nodes.return_value.lxc.return_value.delete.return_value = "UPID:delete"
        api.nodes.return_value.tasks.return_value.status.get.return_value = {"status": "stopped", "exitstatus": "OK"}

        px.destroy_container(api, _cfg(), 9100)

        api.nodes.return_value.lxc.return_value.status.stop.post.assert_called_once()
        api.nodes.return_value.lxc.return_value.delete.assert_called_once_with(purge=1)


class TestPctExec(unittest.TestCase):
    def _channel(self, exit_status):
        channel = MagicMock()
        channel.recv_exit_status.return_value = exit_status
        return channel

    def test_returns_stdout_stderr_and_exit_code(self):
        ssh = MagicMock()
        stdout = MagicMock()
        stdout.channel = self._channel(0)
        stdout.read.return_value = b"hello\n"
        stderr = MagicMock()
        stderr.read.return_value = b""
        ssh.exec_command.return_value = (MagicMock(), stdout, stderr)

        out, err, code, timed_out = px.pct_exec(ssh, 9100, "print('hello')", timeout_s=10)

        self.assertEqual(out, "hello\n")
        self.assertEqual(code, 0)
        self.assertFalse(timed_out)
        command = ssh.exec_command.call_args.args[0]
        self.assertIn("pct exec 9100", command)

    def test_flags_exit_code_124_as_a_timeout(self):
        ssh = MagicMock()
        stdout = MagicMock()
        stdout.channel = self._channel(124)
        stdout.read.return_value = b""
        stderr = MagicMock()
        stderr.read.return_value = b""
        ssh.exec_command.return_value = (MagicMock(), stdout, stderr)

        _, _, code, timed_out = px.pct_exec(ssh, 9100, "while True: pass", timeout_s=1)
        self.assertEqual(code, 124)
        self.assertTrue(timed_out)

    def test_survives_an_ssh_level_exception_instead_of_raising(self):
        ssh = MagicMock()
        ssh.exec_command.side_effect = OSError("connection reset")
        out, err, code, timed_out = px.pct_exec(ssh, 9100, "print(1)", timeout_s=10)
        self.assertEqual(code, 1)
        self.assertIn("ssh_exec_failed", err)


class TestFindAndPullFile(unittest.TestCase):
    def test_find_first_file_returns_the_found_path(self):
        ssh = MagicMock()
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        stdout.read.return_value = b"/tmp/media/videos/scene/480p15/MyScene.mp4\n"
        ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        path = px.find_first_file(ssh, 9100, "/tmp/media", ".mp4")
        self.assertEqual(path, "/tmp/media/videos/scene/480p15/MyScene.mp4")

    def test_find_first_file_returns_none_when_nothing_found(self):
        ssh = MagicMock()
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        stdout.read.return_value = b""
        ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        self.assertIsNone(px.find_first_file(ssh, 9100, "/tmp/media", ".mp4"))

    def test_pull_file_decodes_base64_output(self):
        ssh = MagicMock()
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        stdout.read.return_value = base64.b64encode(b"pngbytes")
        ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        raw = px.pull_file(ssh, 9100, "/tmp/output.png")
        self.assertEqual(raw, b"pngbytes")

    def test_pull_file_returns_none_on_nonzero_exit(self):
        ssh = MagicMock()
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 1
        ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        self.assertIsNone(px.pull_file(ssh, 9100, "/tmp/output.png"))


if __name__ == "__main__":
    unittest.main()
