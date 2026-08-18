"""Sandbox execution client - hive-api's only path to running arbitrary
code. Talks to the sandbox-runner service over HTTP for Docker; hive-api
never touches the Docker socket itself - see sandbox-runner/app.py for why
that capability is isolated to its own small service.

SandboxProvider is the swap point: DockerSandboxProvider is real, wired,
and live-verified. ProxmoxSandboxProvider (app/proxmox_client.py has the
mechanics) talks to a remote Proxmox host directly over its REST API + SSH
- no separate proxy service needed the way Docker's local socket did, since
Proxmox's API is already a remote, token-authenticated API like Ollama's or
Qdrant's. It's implemented in full (clone a template LXC per run, exec via
SSH + `pct exec`, always destroy after) but was built while the Proxmox
host was offline, so it's unverified against a real cluster - see
app/proxmox_client.py's docstring for what a live pass needs to confirm.
Every tutor tool (run_python, render_plot, render_animation, ...) codes
against get_sandbox_provider() generically, so switching HIVE_SANDBOX_PROVIDER
to "proxmox" once it's verified needs no changes above this module.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional, Protocol

from pydantic import BaseModel

DEFAULT_SANDBOX_URL = "http://sandbox-runner:8090"


class SandboxResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    # set when capture_media=True and the run wrote /tmp/output.png - see
    # render_plot in tutor_engine.py (Phase 4 Part B: visual tutoring).
    media_kind: Optional[str] = None
    media_base64: Optional[str] = None


class SandboxProvider(Protocol):
    def run(self, code: str, language: str = "python", timeout_s: int = 10,
            capture_media: bool = False, capture_video: bool = False,
            scene_name: str = "") -> SandboxResult: ...


def _post_json(url: str, payload: dict, *, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw or "{}")


class DockerSandboxProvider:
    """Calls the sandbox-runner service, which owns the Docker socket."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.getenv("HIVE_SANDBOX_URL") or DEFAULT_SANDBOX_URL).rstrip("/")

    def run(self, code: str, language: str = "python", timeout_s: int = 10,
            capture_media: bool = False, capture_video: bool = False,
            scene_name: str = "") -> SandboxResult:
        try:
            data = _post_json(
                f"{self.base_url}/run",
                {"code": code, "language": language, "timeout_s": timeout_s, "capture_media": capture_media,
                 "capture_video": capture_video, "scene_name": scene_name},
                timeout=timeout_s + 10,  # give the HTTP hop room beyond the runner's own execution ceiling
            )
        except Exception as exc:
            return SandboxResult(stdout="", stderr=f"sandbox_unreachable: {exc}", exit_code=1, timed_out=False)
        return SandboxResult(**data)


def _manim_exec_code(code: str, scene_name: str) -> str:
    """Same manim-as-subprocess wrapper as sandbox-runner's Docker path
    (sandbox-runner/app.py's _video_wrapper_code) - duplicated rather than
    shared across a package boundary between two independently deployed
    services (hive-api vs. sandbox-runner), but must stay in sync with it
    if the convention (manim -ql, --media_dir /tmp/media) ever changes."""
    return (
        "import pathlib, subprocess, sys\n"
        f"pathlib.Path('/tmp/scene.py').write_text({code!r})\n"
        "r = subprocess.run(\n"
        f"    ['manim', '-ql', '--media_dir', '/tmp/media', '/tmp/scene.py', {scene_name!r}],\n"
        "    capture_output=True, text=True,\n"
        ")\n"
        "sys.stdout.write(r.stdout)\n"
        "sys.stderr.write(r.stderr)\n"
        "sys.exit(r.returncode)\n"
    )


class ProxmoxSandboxProvider:
    """Per run: clone a template LXC, start it, exec the code inside via
    SSH + `pct exec`, pull back any produced media, always stop+destroy the
    clone - the same "throwaway, isolated, always cleaned up" contract as
    DockerSandboxProvider, just running on Proxmox instead of the local
    Docker socket. See app/proxmox_client.py's module docstring for exactly
    what's unverified and needs a live pass once the host is reachable.
    """

    def run(self, code: str, language: str = "python", timeout_s: int = 10,
            capture_media: bool = False, capture_video: bool = False,
            scene_name: str = "") -> SandboxResult:
        if language != "python":
            return SandboxResult(stdout="", stderr=f"unsupported language: {language}",
                                  exit_code=1, timed_out=False)
        if capture_video and not scene_name.strip():
            return SandboxResult(stdout="", stderr="error: scene_name is required for capture_video",
                                  exit_code=1, timed_out=False)

        from app import proxmox_client as px

        try:
            cfg = px.load_config()
        except ValueError as exc:
            return SandboxResult(stdout="", stderr=str(exc), exit_code=1, timed_out=False)

        exec_code = _manim_exec_code(code, scene_name.strip()) if capture_video else code
        if capture_video:
            template_vmid = cfg.visual_template_vmid
        elif capture_media:
            template_vmid = cfg.plot_template_vmid
        else:
            template_vmid = cfg.template_vmid

        try:
            api = px.api_client(cfg)
            vmid = px.clone_template(api, cfg, template_vmid)
        except Exception as exc:
            return SandboxResult(stdout="", stderr=f"proxmox_provision_failed: {exc}",
                                  exit_code=1, timed_out=False)

        stdout = stderr = ""
        exit_code = 1
        timed_out = False
        media_kind = media_base64 = None
        try:
            px.start_container(api, cfg, vmid)
            ssh = px.ssh_client(cfg)
            try:
                stdout, stderr, exit_code, timed_out = px.pct_exec(ssh, vmid, exec_code, timeout_s)
                if exit_code == 0 and not timed_out:
                    if capture_video:
                        path = px.find_first_file(ssh, vmid, "/tmp/media", ".mp4")
                        raw = px.pull_file(ssh, vmid, path) if path else None
                        if raw:
                            media_kind = "video/mp4"
                    elif capture_media:
                        raw = px.pull_file(ssh, vmid, "/tmp/output.png")
                        if raw:
                            media_kind = "image/png"
                    else:
                        raw = None
                    if raw:
                        import base64
                        media_base64 = base64.b64encode(raw).decode("ascii")
            finally:
                ssh.close()
        except Exception as exc:
            stderr = (stderr + "\n" if stderr else "") + f"proxmox_exec_failed: {exc}"
            exit_code = 1
        finally:
            # always attempted, even if provisioning succeeded but exec
            # blew up - never leave a clone running unnoticed.
            px.destroy_container(api, cfg, vmid)

        return SandboxResult(stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=timed_out,
                              media_kind=media_kind, media_base64=media_base64)


def get_sandbox_provider() -> SandboxProvider:
    kind = (os.getenv("HIVE_SANDBOX_PROVIDER") or "docker").strip().lower()
    if kind == "proxmox":
        return ProxmoxSandboxProvider()
    return DockerSandboxProvider()
