"""sandbox-runner - the only thing in this stack with Docker socket access.

Owns exactly one capability: "run this code in a throwaway, network-less,
resource-capped container and hand back stdout/stderr/exit_code." hive-api
never touches Docker directly (see app/sandbox_client.py) - it calls this
service over the compose-internal network instead, so the blast radius of
"something that can execute arbitrary code" stays inside this one small,
auditable component. Not exposed to the host or internet; only reachable
from other containers on the compose network.
"""
import logging

import docker
from docker.errors import ImageNotFound
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sandbox-runner")

IMAGE = "python:3.12-slim"
MAX_TIMEOUT_S = 30
MEM_LIMIT = "256m"
NANO_CPUS = int(0.5 * 1_000_000_000)  # 0.5 CPU

client = docker.from_env()
app = FastAPI(title="sandbox-runner")


class RunRequest(BaseModel):
    code: str
    language: str = "python"
    timeout_s: int = 10


class RunResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


@app.on_event("startup")
def _ensure_image():
    try:
        client.images.get(IMAGE)
    except ImageNotFound:
        log.info("pulling sandbox base image %s", IMAGE)
        client.images.pull(IMAGE)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/run", response_model=RunResult)
def run(req: RunRequest):
    if req.language != "python":
        return RunResult(stdout="", stderr=f"unsupported language: {req.language}",
                          exit_code=1, timed_out=False)

    timeout_s = max(1, min(req.timeout_s, MAX_TIMEOUT_S))

    container = client.containers.run(
        IMAGE, ["python", "-c", req.code],
        detach=True,
        network_disabled=True,
        mem_limit=MEM_LIMIT,
        nano_cpus=NANO_CPUS,
        pids_limit=64,
        read_only=True,
        tmpfs={"/tmp": "size=16m"},
        user="nobody",
        stdout=True, stderr=True,
    )
    timed_out = False
    exit_code = 1
    stdout = stderr = ""
    try:
        try:
            result = container.wait(timeout=timeout_s)
            exit_code = result.get("StatusCode", 1)
        except Exception:
            timed_out = True
            exit_code = 124
            try:
                container.kill()
            except Exception:
                pass  # already exited between the wait-timeout and here
        try:
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", "replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", "replace")
        except Exception:
            log.exception("failed to read logs from sandbox container %s", container.id)
    finally:
        # always clean up, even if wait()/logs() raised - never leave a
        # container behind, timed out or not
        try:
            container.remove(force=True)
        except Exception:
            log.exception("failed to remove sandbox container %s", container.id)

    return RunResult(stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=timed_out)
