"""Chunk model helpers for Scholar sources.

Phase C begins with durable chunks. This file only stores and lists chunks;
the actual chunking algorithm lands in the next patch.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

from sqlmodel import Session, select

from app.models import LearningSource, LearningSourceChunk, LearningSourceSection


def _json_dump(value: object, fallback: object) -> str:
    try:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False)
    except TypeError:
        return json.dumps(fallback, ensure_ascii=False)


def _json_load(value: str, fallback: object) -> object:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def estimate_tokens(text: str) -> int:
    """Cheap deterministic token estimate for local scheduling/storage.

    This is not model tokenization. It is a stable approximation used before
    embeddings exist. Keep it simple so tests and chunk hashes stay predictable.
    """
    clean = _clean_text(text)
    if not clean:
        return 0
    return max(1, round(len(clean.split()) * 1.33))


def _hash_chunk(source_id: int, position: int, heading: str, body_text: str) -> str:
    raw = f"{source_id}:{position}:{heading}:{body_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _next_position(session: Session, source_id: int) -> int:
    rows = session.exec(
        select(LearningSourceChunk.position)
        .where(LearningSourceChunk.source_id == source_id)
        .order_by(LearningSourceChunk.position.desc())
    ).all()
    return (rows[0] + 1) if rows else 1


def chunk_to_dict(chunk: LearningSourceChunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "source_id": chunk.source_id,
        "section_id": chunk.section_id,
        "position": chunk.position,
        "section_position": chunk.section_position,
        "heading": chunk.heading,
        "heading_path": _json_load(chunk.heading_path_json, []),
        "body_text": chunk.body_text,
        "char_count": chunk.char_count,
        "token_estimate": chunk.token_estimate,
        "chunk_hash": chunk.chunk_hash,
        "metadata": _json_load(chunk.metadata_json, {}),
        "created_at": chunk.created_at.isoformat(),
    }


def create_source_chunk(session: Session, spec: dict[str, Any]) -> dict[str, Any]:
    source_id = int(spec.get("source_id") or 0)
    source = session.get(LearningSource, source_id)
    if not source:
        raise ValueError("source_not_found")

    section_id_raw = spec.get("section_id")
    section_id = int(section_id_raw) if section_id_raw else None
    section_position = int(spec.get("section_position") or 0)
    if section_id is not None:
        section = session.get(LearningSourceSection, section_id)
        if not section or section.source_id != source_id:
            raise ValueError("section_not_found")
        section_position = section.position

    body_text = _clean_text(spec.get("body_text"))
    if not body_text:
        raise ValueError("body_text_required")

    position = int(spec.get("position") or _next_position(session, source_id))
    heading = _clean_text(spec.get("heading"))
    chunk_hash = _clean_text(spec.get("chunk_hash")) or _hash_chunk(source_id, position, heading, body_text)
    existing = session.exec(
        select(LearningSourceChunk)
        .where(
            LearningSourceChunk.source_id == source_id,
            LearningSourceChunk.chunk_hash == chunk_hash,
        )
    ).first()
    if existing:
        return chunk_to_dict(existing)

    heading_path = spec.get("heading_path") or []
    if isinstance(heading_path, str):
        heading_path = [heading_path] if heading_path.strip() else []

    chunk = LearningSourceChunk(
        source_id=source_id,
        section_id=section_id,
        position=position,
        section_position=section_position,
        heading=heading,
        heading_path_json=_json_dump(heading_path, []),
        body_text=body_text,
        char_count=len(body_text),
        token_estimate=int(spec.get("token_estimate") or estimate_tokens(body_text)),
        chunk_hash=chunk_hash,
        metadata_json=_json_dump(spec.get("metadata"), {}),
        created_at=datetime.now(),
    )
    session.add(chunk)
    session.commit()
    session.refresh(chunk)
    return chunk_to_dict(chunk)


def list_source_chunks(session: Session, source_id: int) -> list[dict[str, Any]] | None:
    if not session.get(LearningSource, source_id):
        return None
    rows = session.exec(
        select(LearningSourceChunk)
        .where(LearningSourceChunk.source_id == source_id)
        .order_by(LearningSourceChunk.position)
    ).all()
    return [chunk_to_dict(row) for row in rows]
