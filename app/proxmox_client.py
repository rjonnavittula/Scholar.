"""Low-level Proxmox VE mechanics for ProxmoxSandboxProvider (app/sandbox_client.py).

Built while the Proxmox host was offline (per the tutor Phase 2 plan) - the
calls below follow Proxmox VE's documented REST API and CLI behavior, but
none of it has been exercised against a real host yet. Structurally
complete, functionally unverified - do a live pass (confirm auth, confirm
the clone/start/exec/destroy cycle actually completes, confirm timeouts
and cleanup behave under real network latency) before relying on this.

Why SSH is in the mix at all: Proxmox's REST API has no endpoint to execute
a command inside an LXC container (unlike QEMU VMs, which expose exec via
the guest agent). The documented way to run something inside an LXC from
outside is `pct exec <vmid> -- <command>` on the Proxmox host itself, so
this SSHes in and shells out to that - same trust model as sandbox-runner
shelling out to `docker run` via the Docker socket: whoever holds these
credentials can run pct exec as this user.

Isolation note: this does NOT strip networking from the clone itself -
that's a property of the template (configure it with no net0, or a net0
attached to an isolated/firewalled bridge, so every clone inherits "no
outbound network" the way Docker's network_disabled=True does per-run).
"""
from __future__ import annotations

import base64
import logging
import os
import shlex
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("proxmox_client")


@dataclass
class ProxmoxConfig:
    host: str
    port: int
    node: str
    token_id: str
    token_secret: str
    verify_ssl: bool
    storage: str
    clone_full: bool
    template_vmid: int
    plot_template_vmid: int
    visual_template_vmid: int
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_key_path: str


def load_config() -> ProxmoxConfig:
    """Reads HIVE_PROXMOX_* env vars. Raises ValueError naming exactly which
    ones are missing, rather than partially configuring and failing
    confusingly deep inside a clone/exec call."""
    host = os.getenv("HIVE_PROXMOX_HOST", "").strip()
    node = os.getenv("HIVE_PROXMOX_NODE", "").strip()
    token_id = os.getenv("HIVE_PROXMOX_TOKEN_ID", "").strip()
    token_secret = os.getenv("HIVE_PROXMOX_TOKEN_SECRET", "").strip()
    template_vmid = os.getenv("HIVE_PROXMOX_TEMPLATE_VMID", "").strip()
    storage = os.getenv("HIVE_PROXMOX_STORAGE", "").strip()
    ssh_user = os.getenv("HIVE_PROXMOX_SSH_USER", "").strip()
    ssh_key_path = os.getenv("HIVE_PROXMOX_SSH_KEY_PATH", "").strip()

    missing = [name for name, val in [
        ("HIVE_PROXMOX_HOST", host), ("HIVE_PROXMOX_NODE", node),
        ("HIVE_PROXMOX_TOKEN_ID", token_id), ("HIVE_PROXMOX_TOKEN_SECRET", token_secret),
        ("HIVE_PROXMOX_TEMPLATE_VMID", template_vmid), ("HIVE_PROXMOX_STORAGE", storage),
        ("HIVE_PROXMOX_SSH_USER", ssh_user), ("HIVE_PROXMOX_SSH_KEY_PATH", ssh_key_path),
    ] if not val]
    if missing:
        raise ValueError(f"proxmox_not_configured: missing {', '.join(missing)}")

    # Plot/visual templates default to the base one - start with a single
    # all-in-one template (python3 + matplotlib + manim/ffmpeg/LaTeX) and
    # split into specialized templates later, mirroring how the Docker path
    # has three separate images but didn't start that way.
    base_vmid = int(template_vmid)
    return ProxmoxConfig(
        host=host,
        port=int(os.getenv("HIVE_PROXMOX_PORT", "8006")),
        node=node,
        token_id=token_id,
        token_secret=token_secret,
        verify_ssl=(os.getenv("HIVE_PROXMOX_VERIFY_SSL", "false").strip().lower() == "true"),
        storage=storage,
        clone_full=(os.getenv("HIVE_PROXMOX_CLONE_FULL", "true").strip().lower() != "false"),
        template_vmid=base_vmid,
        plot_template_vmid=int(os.getenv("HIVE_PROXMOX_PLOT_TEMPLATE_VMID", "") or base_vmid),
        visual_template_vmid=int(os.getenv("HIVE_PROXMOX_VISUAL_TEMPLATE_VMID", "") or base_vmid),
        ssh_host=os.getenv("HIVE_PROXMOX_SSH_HOST", "").strip() or host,
        ssh_port=int(os.getenv("HIVE_PROXMOX_SSH_PORT", "22")),
        ssh_user=ssh_user,
        ssh_key_path=ssh_key_path,
    )


def api_client(cfg: ProxmoxConfig):
    from proxmoxer import ProxmoxAPI

    user, _, token_name = cfg.token_id.partition("!")
    if not token_name:
        raise ValueError(f"HIVE_PROXMOX_TOKEN_ID must be 'user@realm!token-name', got {cfg.token_id!r}")
    return ProxmoxAPI(
        cfg.host, port=cfg.port, user=user, token_name=token_name,
        token_value=cfg.token_secret, verify_ssl=cfg.verify_ssl,
    )


def ssh_client(cfg: ProxmoxConfig):
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(cfg.ssh_host, port=cfg.ssh_port, username=cfg.ssh_user,
                    key_filename=cfg.ssh_key_path, timeout=10)
    return client


def wait_for_task(api, node: str, upid: str, timeout_s: float = 60) -> None:
    """Polls a Proxmox task (clone/start/stop/destroy all return a UPID)
    until it's done. Raises RuntimeError on failure or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = api.nodes(node).tasks(upid).status.get()
        if status.get("status") == "stopped":
            if status.get("exitstatus") != "OK":
                raise RuntimeError(f"proxmox_task_failed: {upid}: {status.get('exitstatus')}")
            return
        time.sleep(0.5)
    raise RuntimeError(f"proxmox_task_timeout: {upid}")


def next_vmid(api) -> int:
    return int(api.cluster.nextid.get())


def clone_template(api, cfg: ProxmoxConfig, template_vmid: int) -> int:
    new_vmid = next_vmid(api)
    upid = api.nodes(cfg.node).lxc(template_vmid).clone.post(
        newid=new_vmid, storage=cfg.storage, full=1 if cfg.clone_full else 0,
    )
    wait_for_task(api, cfg.node, upid, timeout_s=120)
    return new_vmid


def start_container(api, cfg: ProxmoxConfig, vmid: int) -> None:
    upid = api.nodes(cfg.node).lxc(vmid).status.start.post()
    wait_for_task(api, cfg.node, upid, timeout_s=60)


def destroy_container(api, cfg: ProxmoxConfig, vmid: int) -> None:
    """Best-effort stop + destroy - always attempted, errors logged not
    raised, mirroring sandbox-runner's container.remove(force=True) in a
    finally block: a cleanup failure must never mask the run's own result,
    but must also never silently leave a container behind unnoticed."""
    try:
        upid = api.nodes(cfg.node).lxc(vmid).status.stop.post()
        wait_for_task(api, cfg.node, upid, timeout_s=30)
    except Exception:
        log.exception("failed to stop proxmox lxc %s", vmid)
    try:
        upid = api.nodes(cfg.node).lxc(vmid).delete(purge=1)
        wait_for_task(api, cfg.node, upid, timeout_s=30)
    except Exception:
        log.exception("failed to destroy proxmox lxc %s", vmid)


def pct_exec(ssh, vmid: int, code: str, timeout_s: int) -> tuple[str, str, int, bool]:
    """Runs `pct exec <vmid> -- ...python3...` over SSH. code travels as
    base64 to sidestep quoting across three shells in a row (local ssh
    command -> pct exec's own arg parsing -> the LXC's shell); wrapped in
    the LXC's own `timeout` command as the primary enforcement, with the
    SSH-level timeout as a backstop if that somehow doesn't fire."""
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    inner = f"echo {encoded} | base64 -d | timeout {timeout_s}s python3 -"
    command = f"pct exec {vmid} -- sh -c {shlex.quote(inner)}"

    timed_out = False
    exit_code = 1
    out = err = ""
    try:
        _stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout_s + 15)
        try:
            exit_code = stdout.channel.recv_exit_status()
        except Exception:
            timed_out = True
            exit_code = 124
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
    except Exception as exc:
        err = f"ssh_exec_failed: {exc}"
    if exit_code == 124:
        timed_out = True
    return out, err, exit_code, timed_out


def find_first_file(ssh, vmid: int, root: str, suffix: str) -> Optional[str]:
    """`find <root> -name '*<suffix>'` inside the LXC, first match. Used for
    render_animation's output, whose exact nested path varies by manim
    version/quality preset - same reasoning as sandbox-runner's
    _extract_first_mp4 for the Docker path."""
    inner = f"find {shlex.quote(root)} -name {shlex.quote('*' + suffix)} 2>/dev/null | head -1"
    command = f"pct exec {vmid} -- sh -c {shlex.quote(inner)}"
    try:
        _stdin, stdout, _stderr = ssh.exec_command(command, timeout=15)
        stdout.channel.recv_exit_status()
        path = stdout.read().decode("utf-8", "replace").strip()
    except Exception:
        return None
    return path or None


def pull_file(ssh, vmid: int, remote_path: str) -> Optional[bytes]:
    """Reads a file out of the LXC via `pct exec ... base64 <path>`,
    avoiding a separate `pct pull` round trip (which writes to a local file
    path on the Proxmox host - an extra step this doesn't need)."""
    inner = f"base64 {shlex.quote(remote_path)} 2>/dev/null"
    command = f"pct exec {vmid} -- sh -c {shlex.quote(inner)}"
    try:
        _stdin, stdout, _stderr = ssh.exec_command(command, timeout=30)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            return None
        raw_b64 = stdout.read().decode("ascii", "replace").strip()
    except Exception:
        return None
    if not raw_b64:
        return None
    try:
        return base64.b64decode(raw_b64)
    except Exception:
        return None
