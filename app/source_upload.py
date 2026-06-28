"""File upload extraction for Scholar source intake.

This is intake only: upload bytes -> safe text source spec.
Parsing/chunking/indexing stay as separate explicit steps.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css"}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    raise ValueError("file_decode_failed")


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"Page {index}\n{text}")
    except Exception as exc:  # pypdf raises several parser-specific exceptions.
        raise ValueError("pdf_extract_failed") from exc

    body = "\n\n".join(pages).strip()
    if not body:
        raise ValueError("pdf_text_required")
    return body


def infer_source_type(filename: str, content_type: str = "") -> str:
    suffix = Path(filename or "").suffix.lower()
    mime = (content_type or "").lower()
    if suffix == ".pdf" or "pdf" in mime:
        return "pdf"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in TEXT_EXTENSIONS or mime.startswith("text/"):
        return "text"
    return "text"


def build_upload_source_spec(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    title: str = "",
    source_type: str = "auto",
    trust_level: str = "user",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not data:
        raise ValueError("file_required")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("file_too_large")

    original_name = Path(filename or "upload.txt").name
    clean_source_type = _clean(source_type or "auto").lower()
    if clean_source_type == "auto":
        clean_source_type = infer_source_type(original_name, content_type)

    if clean_source_type == "pdf":
        body_text = _extract_pdf_text(data)
    else:
        body_text = _decode_text(data)

    if not body_text:
        raise ValueError("file_text_required")

    clean_title = _clean(title)
    if not clean_title:
        clean_title = Path(original_name).stem.replace("_", " ").replace("-", " ").strip() or "Uploaded Source"

    meta = dict(metadata or {})
    meta.update({
        "origin": "file-upload",
        "size_bytes": len(data),
        "inferred_source_type": infer_source_type(original_name, content_type),
    })

    return {
        "title": clean_title,
        "source_type": clean_source_type,
        "trust_level": _clean(trust_level or "user").lower(),
        "mime_type": _clean(content_type or "application/octet-stream"),
        "original_name": original_name,
        "body_text": body_text,
        "metadata": meta,
    }
