"""On-disk storage for tutor-generated media (Phase 4 Part B: visual tutoring).

Binary blobs (plot images, later animations) don't belong inlined into
TutorMessage.content as base64 - that table gets loaded wholesale on every
chat open, which is fine for text and bad for embedded images. Instead
they're written here under a UUID filename (never model- or user-supplied,
so there's no path-traversal surface) and served back by an authenticated
route in app/api.py.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

MEDIA_ROOT = Path(os.getenv("HIVE_MEDIA_DIR", "/app/media"))

_EXT_BY_KIND = {"image/png": ".png"}
_KIND_BY_EXT = {v: k for k, v in _EXT_BY_KIND.items()}


def save_media(track_id: int, kind: str, raw_bytes: bytes) -> str:
    """Writes raw_bytes to disk, returns the URL path to fetch it back at."""
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    ext = _EXT_BY_KIND.get(kind, "")
    filename = f"{track_id}_{uuid.uuid4().hex}{ext}"
    (MEDIA_ROOT / filename).write_bytes(raw_bytes)
    return f"/learn/tutor/media/{filename}"


def read_media(filename: str) -> bytes | None:
    """Reads a previously-saved file back by its bare filename. Rejects
    anything with a path separator or a '..' segment - save_media never
    produces one, so this only ever blocks a hostile filename param."""
    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        return None
    path = MEDIA_ROOT / filename
    try:
        if path.resolve().parent != MEDIA_ROOT.resolve():
            return None
    except OSError:
        return None
    if not path.is_file():
        return None
    return path.read_bytes()


def media_content_type(filename: str) -> str:
    return _KIND_BY_EXT.get(Path(filename).suffix, "application/octet-stream")
