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
MAX_VIDEO_TIMEOUT_S = 90  # manim renders, even at low quality, are slow
MEM_LIMIT = "256m"
NANO_CPUS = int(0.5 * 1_000_000_000)  # 0.5 CPU
MEDIA_PATH = "/tmp/output.png"
VIDEO_DIR = "/tmp/media"

# A derived image with matplotlib for render_plot calls (Phase 4 Part B).
# Built once, lazily, straight from an in-memory Dockerfile - matplotlib
# has to live in the throwaway per-request container (this service's own
# venv never executes user code), so there's no host Dockerfile to keep in
# sync; the daemon just caches the built image like any pulled one.
PLOT_IMAGE = "hive-sandbox-plot:latest"
PLOT_DOCKERFILE = b"FROM python:3.12-slim\nRUN pip install --no-cache-dir matplotlib\n"

# The Manim/LaTeX image (Phase 4 Part C) is big and slow to build (LaTeX
# alone is hundreds of MB) - unlike PLOT_IMAGE it is NOT built lazily here.
# It's a real Dockerfile at sandbox-runner/images/visual.Dockerfile, built
# explicitly via `docker compose build sandbox-visual-image`. Building it
# on a request thread would blow past the HTTP timeout hive-api's client
# uses; if it's missing, /run just returns a clear error instead of trying.
VISUAL_IMAGE = "hive-sandbox-visual:latest"

client = docker.from_env()
app = FastAPI(title="sandbox-runner")


class RunRequest(BaseModel):
    code: str
    language: str = "python"
    timeout_s: int = 10
    capture_media: bool = False
    capture_video: bool = False
    scene_name: str = ""


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
    try:
        client.images.get(VISUAL_IMAGE)
    except ImageNotFound:
        log.warning(
            "%s not found - render_animation will fail until it's built with "
            "`docker compose build sandbox-visual-image` (slow: LaTeX + manim)",
            VISUAL_IMAGE,
        )


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


def _video_wrapper_code(code: str, scene_name: str) -> str:
    """Runs `manim` as a subprocess rather than importing it in-process, so
    its own stdout/stderr and exit code can just be forwarded as this run's -
    same "the sandboxed process's output IS the result" contract run_python
    and render_plot already have, no manim-specific parsing needed here."""
    return (
        "import pathlib, subprocess, sys\n"
        f"pathlib.Path('/tmp/scene.py').write_text({code!r})\n"
        "r = subprocess.run(\n"
        f"    ['manim', '-ql', '--media_dir', {VIDEO_DIR!r}, '/tmp/scene.py', {scene_name!r}],\n"
        "    capture_output=True, text=True,\n"
        ")\n"
        "sys.stdout.write(r.stdout)\n"
        "sys.stderr.write(r.stderr)\n"
        "sys.exit(r.returncode)\n"
    )


def _extract_first_mp4(container, root: str = VIDEO_DIR) -> tuple[Optional[str], Optional[str]]:
    """Same idea as _extract_png, but manim's output path (media/videos/<scene
    file stem>/<quality>/<scene_name>.mp4) varies by version/quality preset,
    so this fetches the whole media dir and takes the first .mp4 found rather
    than hardcoding the nested path."""
    import base64

    try:
        stream, _stat = container.get_archive(root)
    except NotFound:
        return None, None
    except Exception:
        log.exception("failed to read %s from sandbox container %s", root, container.id)
        return None, None

    buf = io.BytesIO()
    for chunk in stream:
        buf.write(chunk)
    buf.seek(0)
    try:
        with tarfile.open(fileobj=buf) as tar:
            member = next((m for m in tar.getmembers() if m.name.endswith(".mp4")), None)
            if member is None:
                return None, None
            f = tar.extractfile(member)
            raw = f.read() if f else b""
    except Exception:
        log.exception("failed to unpack an mp4 from %s in sandbox container %s", root, container.id)
        return None, None

    if not raw:
        return None, None
    return "video/mp4", base64.b64encode(raw).decode("ascii")


@app.post("/run", response_model=RunResult)
def run(req: RunRequest):
    if req.language != "python":
        return RunResult(stdout="", stderr=f"unsupported language: {req.language}",
                          exit_code=1, timed_out=False)

    if req.capture_video:
        if not req.scene_name.strip():
            return RunResult(stdout="", stderr="error: scene_name is required for capture_video",
                              exit_code=1, timed_out=False)
        try:
            client.images.get(VISUAL_IMAGE)
        except ImageNotFound:
            return RunResult(
                stdout="", exit_code=1, timed_out=False,
                stderr=(f"error: {VISUAL_IMAGE} isn't built yet - run "
                        "`docker compose build sandbox-visual-image` (slow: LaTeX + manim)"),
            )

    timeout_s = max(1, min(req.timeout_s, MAX_VIDEO_TIMEOUT_S if req.capture_video else MAX_TIMEOUT_S))
    if req.capture_video:
        image = VISUAL_IMAGE
        exec_code = _video_wrapper_code(req.code, req.scene_name.strip())
    elif req.capture_media:
        image = PLOT_IMAGE
        exec_code = req.code
    else:
        image = IMAGE
        exec_code = req.code

    run_kwargs = dict(
        detach=True,
        network_disabled=True,
        mem_limit=MEM_LIMIT,
        nano_cpus=NANO_CPUS,
        pids_limit=64,
        user="nobody",
        stdout=True, stderr=True,
    )
    if req.capture_media or req.capture_video:
        # NOT read_only + tmpfs here: get_archive() below reads the file back
        # out AFTER the container has already stopped, and a tmpfs mount is
        # torn down with the container's mount namespace the moment its main
        # process exits - by the time we'd read it, it's already gone, even
        # though the (stopped, not yet removed) container object still
        # exists. A normal writable overlay layer persists until remove(),
        # so /tmp/output.png or /tmp/media is still there to fetch.
        run_kwargs["read_only"] = False
    else:
        run_kwargs["read_only"] = True
        run_kwargs["tmpfs"] = {"/tmp": "size=16m"}

    container = client.containers.run(image, ["python", "-c", exec_code], **run_kwargs)
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
        elif req.capture_video and exit_code == 0 and not timed_out:
            media_kind, media_base64 = _extract_first_mp4(container)
    finally:
        # always clean up, even if wait()/logs() raised - never leave a
        # container behind, timed out or not
        try:
            container.remove(force=True)
        except Exception:
            log.exception("failed to remove sandbox container %s", container.id)

    return RunResult(stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=timed_out,
                      media_kind=media_kind, media_base64=media_base64)
