"""Source registry helpers for Scholar courses.

Phase B begins here: store trusted learning material first. Parsing, chunking,
embeddings, and RAG are intentionally later steps.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from app.models import LearningSource, LearningTrack, LearningTrackSource

ALLOWED_SOURCE_TYPES = {"text", "markdown", "pdf", "url", "syllabus"}
ALLOWED_TRUST_LEVELS = {"user", "course", "official", "web"}


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


def _hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _source_to_dict(source: LearningSource) -> dict[str, Any]:
    return {
        "id": source.id,
        "title": source.title,
        "source_type": source.source_type,
        "trust_level": source.trust_level,
        "status": source.status,
        "content_hash": source.content_hash,
        "mime_type": source.mime_type,
        "original_name": source.original_name,
        "char_count": len(source.body_text or ""),
        "metadata": _json_load(source.metadata_json, {}),
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
    }


def _source_detail_to_dict(source: LearningSource) -> dict[str, Any]:
    out = _source_to_dict(source)
    out["body_text"] = source.body_text
    return out


def list_sources(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(select(LearningSource).order_by(LearningSource.created_at.desc())).all()
    return [_source_to_dict(row) for row in rows]


def get_source(session: Session, source_id: int) -> dict[str, Any] | None:
    source = session.get(LearningSource, source_id)
    return _source_detail_to_dict(source) if source else None


def create_source(session: Session, spec: dict[str, Any]) -> dict[str, Any]:
    body = _clean_text(spec.get("body_text"))
    if not body:
        raise ValueError("body_text_required")

    source_type = _clean_text(spec.get("source_type") or "text").lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError("invalid_source_type")

    trust_level = _clean_text(spec.get("trust_level") or "user").lower()
    if trust_level not in ALLOWED_TRUST_LEVELS:
        raise ValueError("invalid_trust_level")

    title = _clean_text(spec.get("title"))
    if not title:
        title = body.splitlines()[0].strip()[:80] or "Untitled Source"

    now = datetime.now()
    source = LearningSource(
        title=title,
        source_type=source_type,
        trust_level=trust_level,
        status="registered",
        content_hash=_hash_body(body),
        mime_type=_clean_text(spec.get("mime_type") or "text/plain"),
        original_name=_clean_text(spec.get("original_name")),
        body_text=body,
        metadata_json=_json_dump(spec.get("metadata"), {}),
        created_at=now,
        updated_at=now,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return _source_detail_to_dict(source)


def link_source_to_track(session: Session, track_id: int, source_id: int, role: str = "primary") -> dict[str, Any] | None:
    track = session.get(LearningTrack, track_id)
    source = session.get(LearningSource, source_id)
    if not track or not source:
        return None

    existing = session.exec(
        select(LearningTrackSource).where(
            LearningTrackSource.track_id == track_id,
            LearningTrackSource.source_id == source_id,
        )
    ).first()
    if existing:
        existing.role = _clean_text(role) or "primary"
        session.add(existing)
    else:
        session.add(LearningTrackSource(
            track_id=track_id,
            source_id=source_id,
            role=_clean_text(role) or "primary",
        ))
    track.updated_at = datetime.now()
    session.add(track)
    session.commit()
    return get_source(session, source_id)


def list_track_sources(session: Session, track_id: int) -> list[dict[str, Any]] | None:
    if not session.get(LearningTrack, track_id):
        return None
    links = session.exec(
        select(LearningTrackSource)
        .where(LearningTrackSource.track_id == track_id)
        .order_by(LearningTrackSource.created_at)
    ).all()

    rows: list[dict[str, Any]] = []
    for link in links:
        source = session.get(LearningSource, link.source_id)
        if source:
            item = _source_to_dict(source)
            item["role"] = link.role
            rows.append(item)
    return rows


def delete_source(session: Session, source_id: int) -> bool:
    source = session.get(LearningSource, source_id)
    if not source:
        return False
    session.exec(delete(LearningTrackSource).where(LearningTrackSource.source_id == source_id))
    session.delete(source)
    session.commit()
    return True
