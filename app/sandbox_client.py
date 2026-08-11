"""Sandbox execution client - hive-api's only path to running arbitrary
code. Talks to the sandbox-runner service over HTTP; hive-api never touches
Docker (or, later, Proxmox) directly - see sandbox-runner/app.py for why
that capability is isolated to its own small service.

SandboxProvider is the swap point: DockerSandboxProvider is real and wired
today; ProxmoxSandboxProvider is scaffolded for when the Proxmox host (per
the tutor Phase 2 plan) comes back online. Phase 3's tool-calling loop can
code against get_sandbox_provider() without caring which backend is live.
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
            capture_media: bool = False) -> SandboxResult: ...


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
            capture_media: bool = False) -> SandboxResult:
        try:
            data = _post_json(
                f"{self.base_url}/run",
                {"code": code, "language": language, "timeout_s": timeout_s, "capture_media": capture_media},
                timeout=timeout_s + 10,  # give the HTTP hop room beyond the runner's own execution ceiling
            )
        except Exception as exc:
            return SandboxResult(stdout="", stderr=f"sandbox_unreachable: {exc}", exit_code=1, timed_out=False)
        return SandboxResult(**data)


class ProxmoxSandboxProvider:
    """Scaffolded, not implemented. The Proxmox host was offline when this
    was built (see the tutor Phase 2 plan), so its API surface was never
    verified - this exists purely so Phase 3's tool-calling loop can be
    written against SandboxProvider generically now, and wiring real
    Proxmox API calls in here later (via proxmoxer) is additive, not a
    rewrite. Deliberately raises rather than silently no-op'ing or guessing
    at untested API calls.
    """

    def run(self, code: str, language: str = "python", timeout_s: int = 10,
            capture_media: bool = False) -> SandboxResult:
        raise NotImplementedError(
            "ProxmoxSandboxProvider isn't implemented yet - the Proxmox host was "
            "offline when this was scaffolded, so nothing here has been verified "
            "against a real API. Leave HIVE_SANDBOX_PROVIDER unset (or 'docker') "
            "until this is wired up and tested."
        )


def get_sandbox_provider() -> SandboxProvider:
    kind = (os.getenv("HIVE_SANDBOX_PROVIDER") or "docker").strip().lower()
    if kind == "proxmox":
        return ProxmoxSandboxProvider()
    return DockerSandboxProvider()
