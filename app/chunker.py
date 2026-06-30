"""Deterministic chunking engine for parsed Scholar sources.

This is still pre-RAG infrastructure: no embeddings, no Qdrant, no LLM calls.
It turns parsed source sections into stable, smaller chunks that can be indexed
in the next phase.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session

from app.chunk_store import create_source_chunk, list_source_chunks
from app.models import LearningSource, LearningSourceChunk
from app.source_store import get_source, list_source_sections, parse_registered_source

CHUNKER_VERSION = "source-chunker-v1"
DEFAULT_MAX_CHARS = 900
DEFAULT_OVERLAP_CHARS = 120
MIN_MAX_CHARS = 240
MAX_MAX_CHARS = 4_000
MAX_OVERLAP_CHARS = 500


def _clean_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _clean_int(value: object, default: int, *, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(number, high))


def _best_window_end(text: str, start: int, hard_end: int, min_end: int) -> int:
    """Find a readable chunk boundary without doing anything magical."""
    if hard_end >= len(text):
        return len(text)

    window = text[start:hard_end]
    candidates: list[int] = []
    for marker in ("\n\n", ". ", "? ", "! ", "\n", "; ", ", ", " "):
        idx = window.rfind(marker)
        if idx >= 0:
            candidates.append(start + idx + len(marker.rstrip()))

    usable = [idx for idx in candidates if idx >= min_end]
    return max(usable) if usable else hard_end


def split_text_for_chunks(text: str, *, max_chars: int = DEFAULT_MAX_CHARS, overlap_chars: int = DEFAULT_OVERLAP_CHARS) -> list[str]:
    """Split one section body into deterministic text windows.

    Overlap is intentionally character based. It is not semantic; it simply
    keeps local context together before embeddings exist.
    """
    body = _clean_text(text)
    if not body:
        return []

    max_chars = _clean_int(max_chars, DEFAULT_MAX_CHARS, low=MIN_MAX_CHARS, high=MAX_MAX_CHARS)
    overlap_chars = _clean_int(overlap_chars, DEFAULT_OVERLAP_CHARS, low=0, high=min(MAX_OVERLAP_CHARS, max_chars // 3))

    if len(body) <= max_chars:
        return [body]

    chunks: list[str] = []
    start = 0
    while start < len(body):
        hard_end = min(len(body), start + max_chars)
        min_end = min(len(body), start + max(max_chars // 2, 1))
        end = _best_window_end(body, start, hard_end, min_end)
        chunk = body[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(body):
            break

        next_start = max(start + 1, end - overlap_chars)
        while next_start < len(body) and body[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks


def build_chunk_specs(source_id: int, sections: list[dict[str, Any]], *, max_chars: int = DEFAULT_MAX_CHARS, overlap_chars: int = DEFAULT_OVERLAP_CHARS) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    position = 1
    ordered_sections = sorted(sections, key=lambda row: int(row.get("position") or 0))

    for section in ordered_sections:
        section_id = section.get("id")
        section_position = int(section.get("position") or 0)
        heading = _clean_text(section.get("heading")) or f"Section {section_position or position}"
        body = _clean_text(section.get("body_text"))
        if not body:
            continue

        metadata = section.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        heading_path = metadata.get("heading_path") or [heading]
        parts = split_text_for_chunks(body, max_chars=max_chars, overlap_chars=overlap_chars)
        split_count = len(parts)

        for index, part in enumerate(parts, start=1):
            chunk_heading = heading if split_count == 1 else f"{heading} · part {index}"
            specs.append({
                "source_id": source_id,
                "section_id": section_id,
                "section_position": section_position,
                "position": position,
                "heading": chunk_heading,
                "heading_path": heading_path,
                "body_text": part,
                "metadata": {
                    "chunker_version": CHUNKER_VERSION,
                    "strategy": "section_window",
                    "source_section_hash": section.get("section_hash") or "",
                    "source_section_heading": heading,
                    "source_section_position": section_position,
                    "split_index": index,
                    "split_count": split_count,
                    "max_chars": _clean_int(max_chars, DEFAULT_MAX_CHARS, low=MIN_MAX_CHARS, high=MAX_MAX_CHARS),
                    "overlap_chars": _clean_int(overlap_chars, DEFAULT_OVERLAP_CHARS, low=0, high=min(MAX_OVERLAP_CHARS, _clean_int(max_chars, DEFAULT_MAX_CHARS, low=MIN_MAX_CHARS, high=MAX_MAX_CHARS) // 3)),
                },
            })
            position += 1

    return specs


def chunk_registered_source(session: Session, source_id: int, *, max_chars: int = DEFAULT_MAX_CHARS, overlap_chars: int = DEFAULT_OVERLAP_CHARS, replace: bool = True) -> dict[str, Any] | None:
    """Create durable chunks for one source from its parsed sections."""
    source = session.get(LearningSource, source_id)
    if not source:
        return None

    sections = list_source_sections(session, source_id)
    if sections is None:
        return None
    if not sections:
        parsed = parse_registered_source(session, source_id)
        sections = parsed["sections"] if parsed else []

    specs = build_chunk_specs(source_id, sections, max_chars=max_chars, overlap_chars=overlap_chars)

    if replace:
        session.exec(delete(LearningSourceChunk).where(LearningSourceChunk.source_id == source_id))
        session.commit()

    chunks = [create_source_chunk(session, spec) for spec in specs]
    source.updated_at = datetime.now()
    session.add(source)
    session.commit()

    source_detail = get_source(session, source_id) or {"id": source_id}
    return {
        "source": source_detail,
        "chunker_version": CHUNKER_VERSION,
        "chunk_count": len(chunks),
        "total_chars": sum(int(row["char_count"]) for row in chunks),
        "total_tokens": sum(int(row["token_estimate"]) for row in chunks),
        "chunks": list_source_chunks(session, source_id) or [],
    }
