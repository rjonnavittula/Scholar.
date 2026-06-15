"""HIVE → Super Productivity relay.

Polls the HIVE Tasks API for open tasks and pushes any *new* ones into the
Super Productivity desktop app via the Electron bridge (port 39999).
Remembers what it already sent in a small state file, so it's idempotent —
run it from cron, a systemd timer, or Task Scheduler.

Env:
  HIVE_API_URL     default http://127.0.0.1:8077
  HIVE_API_KEY     required — key from POST /auth/keys
  SP_BRIDGE_URL    default http://127.0.0.1:39999
  SP_BRIDGE_TOKEN  optional — else read from the SP token file
  SP_PROJECT_NAME  optional — map all tasks to one SP project (e.g. "Canvas")

Stdlib only. Pure read from HIVE, pure create into SP. One-way by design (v1).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

STATE_FILE = Path.home() / ".hive-sp-relay.json"


def sp_token() -> str:
    tok = os.getenv("SP_BRIDGE_TOKEN")
    if tok:
        return tok
    # Default Electron userData dirs; the folder name is the Electron app
    # name — if neither exists, `ls` the parent dir and set SP_BRIDGE_TOKEN.
    candidates = []
    if sys.platform == "win32":
        base = Path(os.environ["APPDATA"])
        candidates = [base / "superProductivity", base / "super-productivity"]
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        candidates = [base / "superProductivity", base / "super-productivity"]
    else:
        base = Path.home() / ".config"
        candidates = [base / "superProductivity", base / "super-productivity"]
    for c in candidates:
        p = c / ".external-api-token"
        if p.exists():
            return p.read_text().strip()
    raise SystemExit(
        "SP bridge token not found — set SP_BRIDGE_TOKEN or check the app's userData dir"
    )


def http_json(url: str, headers: dict, data: dict | None = None) -> tuple[int, dict | list]:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={**headers, "Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode() or "null")


def load_seen() -> set[int]:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()).get("sent_ids", []))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def save_seen(seen: set[int]) -> None:
    STATE_FILE.write_text(json.dumps({"sent_ids": sorted(seen)}))


def main() -> None:
    hive = os.getenv("HIVE_API_URL", "http://127.0.0.1:8077").rstrip("/")
    key = os.environ["HIVE_API_KEY"]
    bridge = os.getenv("SP_BRIDGE_URL", "http://127.0.0.1:39999").rstrip("/")
    token = sp_token()
    project = os.getenv("SP_PROJECT_NAME")

    _, tasks = http_json(f"{hive}/tasks?status=todo", {"X-API-Key": key})
    seen = load_seen()
    pushed = 0

    for t in tasks:
        if t["id"] in seen:
            continue
        payload = {
            "title": t["title"],
            "notes": t.get("notes") or "",
            "externalId": f"hive:{t['id']}",
        }
        if t.get("due_at"):
            payload["dueDay"] = t["due_at"][:10]
        if t.get("time_needed_min"):
            payload["timeEstimate"] = int(t["time_needed_min"]) * 60_000  # min → ms
        if project:
            payload["projectName"] = project

        status, _ = http_json(
            f"{bridge}/api/task", {"Authorization": f"Bearer {token}"}, payload
        )
        if status == 202:
            seen.add(t["id"])
            pushed += 1
        else:
            print(f"  ! bridge returned {status} for task {t['id']}", file=sys.stderr)

    save_seen(seen)
    print(f"relay: {pushed} new task(s) pushed, {len(seen)} total tracked")


if __name__ == "__main__":
    main()
