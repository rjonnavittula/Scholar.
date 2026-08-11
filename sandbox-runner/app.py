"""sandbox-runner - the only thing in this stack with Docker socket access.

Owns exactly one capability: "run this code in a throwaway, network-less,
resource-capped container and hand back stdout/stderr/exit_code." hive-api
never touches Docker directly (see app/sandbox_client.py) - it calls this
service over the compose-internal network instead, so the blast radius of
"something that can execute arbitrary code" stays inside this one small,
auditable component. Not exposed to the host or internet; only reachable
from other containers on the compose network.
"""
import io
import logging
import tarfile
from typing import Optional

import docker
from docker.errors import ImageNotFound, NotFound
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sandbox-runner")

IMAGE = "python:3.12-slim"
MAX_TIMEOUT_S = 30
MEM_LIMIT = "256m"
NANO_CPUS = int(0.5 * 1_000_000_000)  # 0.5 CPU
MEDIA_PATH = "/tmp/output.png"

# A derived image with matplotlib for render_plot calls (Phase 4 Part B).
# Built once, lazily, straight from an in-memory Dockerfile - matplotlib
# has to live in the throwaway per-request container (this service's own
# venv never executes user code), so there's no host Dockerfile to keep in
# sync; the daemon just caches the built image like any pulled one.
PLOT_IMAGE = "hive-sandbox-plot:latest"
PLOT_DOCKERFILE = b"FROM python:3.12-slim\nRUN pip install --no-cache-dir matplotlib\n"

client = docker.from_env()
app = FastAPI(title="sandbox-runner")


class RunRequest(BaseModel):
    code: str
    language: str = "python"
    timeout_s: int = 10
    capture_media: bool = False


class RunResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    media_kind: Optional[str] = None
    media_base64: Optional[str] = None


def _build_plot_image():
    log.info("building sandbox plot image %s (matplotlib) - first run only", PLOT_IMAGE)
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        info = tarfile.TarInfo(name="Dockerfile")
        info.size = len(PLOT_DOCKERFILE)
        tar.addfile(info, io.BytesIO(PLOT_DOCKERFILE))
    tar_buf.seek(0)
    client.images.build(fileobj=tar_buf, custom_context=True, tag=PLOT_IMAGE, rm=True)


@app.on_event("startup")
def _ensure_image():
    try:
        client.images.get(IMAGE)
    except ImageNotFound:
        log.info("pulling sandbox base image %s", IMAGE)
        client.images.pull(IMAGE)
    try:
        client.images.get(PLOT_IMAGE)
    except ImageNotFound:
        _build_plot_image()


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _extract_png(container) -> tuple[Optional[str], Optional[str]]:
    """Best-effort read of MEDIA_PATH from a finished container. Returns
    (media_kind, media_base64) or (None, None) - not every render_plot call
    necessarily produces an image (e.g. the model's code errored first), so
    a missing file here is a normal outcome, not a failure to log."""
    import base64

    try:
        stream, _stat = container.get_archive(MEDIA_PATH)
    except NotFound:
        return None, None
    except Exception:
        log.exception("failed to read %s from sandbox container %s", MEDIA_PATH, container.id)
        return None, None

    buf = io.BytesIO()
    for chunk in stream:
        buf.write(chunk)
    buf.seek(0)
    try:
        with tarfile.open(fileobj=buf) as tar:
            member = tar.getmember("output.png")
            f = tar.extractfile(member)
            raw = f.read() if f else b""
    except Exception:
        log.exception("failed to unpack %s from sandbox container %s", MEDIA_PATH, container.id)
        return None, None

    if not raw:
        return None, None
    return "image/png", base64.b64encode(raw).decode("ascii")


@app.post("/run", response_model=RunResult)
def run(req: RunRequest):
    if req.language != "python":
        return RunResult(stdout="", stderr=f"unsupported language: {req.language}",
                          exit_code=1, timed_out=False)

    timeout_s = max(1, min(req.timeout_s, MAX_TIMEOUT_S))
    image = PLOT_IMAGE if req.capture_media else IMAGE

    run_kwargs = dict(
        detach=True,
        network_disabled=True,
        mem_limit=MEM_LIMIT,
        nano_cpus=NANO_CPUS,
        pids_limit=64,
        user="nobody",
        stdout=True, stderr=True,
    )
    if req.capture_media:
        # NOT read_only + tmpfs here: get_archive() below reads the file back
        # out AFTER the container has already stopped, and a tmpfs mount is
        # torn down with the container's mount namespace the moment its main
        # process exits - by the time we'd read it, it's already gone, even
        # though the (stopped, not yet removed) container object still
        # exists. A normal writable overlay layer persists until remove(),
        # so /tmp/output.png is still there to fetch.
        run_kwargs["read_only"] = False
    else:
        run_kwargs["read_only"] = True
        run_kwargs["tmpfs"] = {"/tmp": "size=16m"}

    container = client.containers.run(image, ["python", "-c", req.code], **run_kwargs)
    timed_out = False
    exit_code = 1
    stdout = stderr = ""
    media_kind = media_base64 = None
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
        if req.capture_media and exit_code == 0 and not timed_out:
            media_kind, media_base64 = _extract_png(container)
    finally:
        # always clean up, even if wait()/logs() raised - never leave a
        # container behind, timed out or not
        try:
            container.remove(force=True)
        except Exception:
            log.exception("failed to remove sandbox container %s", container.id)

    return RunResult(stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=timed_out,
                      media_kind=media_kind, media_base64=media_base64)
