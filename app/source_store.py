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

from app.models import LearningSource, LearningSourceChunk, LearningSourceSection, LearningTrack, LearningTrackSource
from app.source_parser import parse_pasted_source

ALLOWED_SOURCE_TYPES = {"text", "markdown", "pdf", "url", "syllabus", "transcript"}
ALLOWED_TRUST_LEVELS = {"user", "course", "official", "web", "instructor", "reference"}
ALLOWED_SOURCE_ROLES = {"primary", "supplemental", "reference"}
MAX_SOURCE_TEXT_CHARS = 250_000


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


def _source_to_dict(source: LearningSource, *, section_count: int = 0, chunk_count: int = 0) -> dict[str, Any]:
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
        "section_count": section_count,
        "chunk_count": chunk_count,
        "metadata": _json_load(source.metadata_json, {}),
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
    }


def _source_detail_to_dict(source: LearningSource, *, deduplicated: bool = False, section_count: int = 0, chunk_count: int = 0) -> dict[str, Any]:
    out = _source_to_dict(source, section_count=section_count, chunk_count=chunk_count)
    out["body_text"] = source.body_text
    out["deduplicated"] = deduplicated
    return out


def _section_to_dict(section: LearningSourceSection) -> dict[str, Any]:
    return {
        "id": section.id,
        "source_id": section.source_id,
        "position": section.position,
        "heading": section.heading,
        "level": section.level,
        "body_text": section.body_text,
        "char_count": section.char_count,
        "section_hash": section.section_hash,
        "metadata": _json_load(section.metadata_json, {}),
        "created_at": section.created_at.isoformat(),
    }


def _section_count(session: Session, source_id: int) -> int:
    return len(session.exec(
        select(LearningSourceSection.id).where(LearningSourceSection.source_id == source_id)
    ).all())


def _chunk_count(session: Session, source_id: int) -> int:
    return len(session.exec(
        select(LearningSourceChunk.id).where(LearningSourceChunk.source_id == source_id)
    ).all())


def _clean_role(role: str = "primary") -> str:
    clean_role = _clean_text(role or "primary").lower()
    if clean_role not in ALLOWED_SOURCE_ROLES:
        raise ValueError("invalid_source_role")
    return clean_role


def list_sources(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(select(LearningSource).order_by(LearningSource.created_at.desc())).all()
    return [_source_to_dict(row, section_count=_section_count(session, row.id or 0), chunk_count=_chunk_count(session, row.id or 0)) for row in rows]


def get_source(session: Session, source_id: int) -> dict[str, Any] | None:
    source = session.get(LearningSource, source_id)
    return _source_detail_to_dict(source, section_count=_section_count(session, source_id), chunk_count=_chunk_count(session, source_id)) if source else None


def list_source_sections(session: Session, source_id: int) -> list[dict[str, Any]] | None:
    if not session.get(LearningSource, source_id):
        return None
    rows = session.exec(
        select(LearningSourceSection)
        .where(LearningSourceSection.source_id == source_id)
        .order_by(LearningSourceSection.position)
    ).all()
    return [_section_to_dict(row) for row in rows]


def parse_registered_source(session: Session, source_id: int) -> dict[str, Any] | None:
    source = session.get(LearningSource, source_id)
    if not source:
        return None

    parsed = parse_pasted_source(source.body_text, source.source_type)
    session.exec(delete(LearningSourceChunk).where(LearningSourceChunk.source_id == source_id))
    session.exec(delete(LearningSourceSection).where(LearningSourceSection.source_id == source_id))

    now = datetime.now()
    for item in parsed["sections"]:
        session.add(LearningSourceSection(
            source_id=source_id,
            position=int(item["position"]),
            heading=_clean_text(item["heading"]) or f"Section {item['position']}",
            level=int(item["level"]),
            body_text=_clean_text(item["body_text"]),
            char_count=int(item["char_count"]),
            section_hash=_clean_text(item["section_hash"]),
            metadata_json=_json_dump(item.get("metadata"), {}),
            created_at=now,
        ))

    source.status = "parsed"
    source.updated_at = now
    session.add(source)
    session.commit()
    session.refresh(source)

    sections = list_source_sections(session, source_id) or []
    return {
        "source": _source_detail_to_dict(source, section_count=len(sections), chunk_count=0),
        "section_count": len(sections),
        "total_chars": sum(int(row["char_count"]) for row in sections),
        "outline": [{
            "position": row["position"],
            "heading": row["heading"],
            "level": row["level"],
        } for row in sections],
        "sections": sections,
    }


def create_source(session: Session, spec: dict[str, Any]) -> dict[str, Any]:
    body = _clean_text(spec.get("body_text"))
    if not body:
        raise ValueError("body_text_required")
    if len(body) > MAX_SOURCE_TEXT_CHARS:
        raise ValueError("body_text_too_large")

    source_type = _clean_text(spec.get("source_type") or "text").lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError("invalid_source_type")

    trust_level = _clean_text(spec.get("trust_level") or "user").lower()
    if trust_level not in ALLOWED_TRUST_LEVELS:
        raise ValueError("invalid_trust_level")

    content_hash = _hash_body(body)
    existing = session.exec(
        select(LearningSource)
        .where(
            LearningSource.content_hash == content_hash,
            LearningSource.source_type == source_type,
            LearningSource.body_text == body,
        )
        .order_by(LearningSource.created_at)
    ).first()
    if existing:
        return _source_detail_to_dict(existing, deduplicated=True, section_count=_section_count(session, existing.id or 0), chunk_count=_chunk_count(session, existing.id or 0))

    title = _clean_text(spec.get("title"))
    if not title:
        title = body.splitlines()[0].strip()[:80] or "Untitled Source"

    now = datetime.now()
    source = LearningSource(
        title=title,
        source_type=source_type,
        trust_level=trust_level,
        status="registered",
        content_hash=content_hash,
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
    return _source_detail_to_dict(source, section_count=0)


def link_source_to_track(session: Session, track_id: int, source_id: int, role: str = "primary") -> dict[str, Any] | None:
    track = session.get(LearningTrack, track_id)
    source = session.get(LearningSource, source_id)
    if not track or not source:
        return None

    clean_role = _clean_role(role)
    existing = session.exec(
        select(LearningTrackSource).where(
            LearningTrackSource.track_id == track_id,
            LearningTrackSource.source_id == source_id,
        )
    ).first()
    if existing:
        existing.role = clean_role
        session.add(existing)
    else:
        session.add(LearningTrackSource(
            track_id=track_id,
            source_id=source_id,
            role=clean_role,
        ))
    track.updated_at = datetime.now()
    session.add(track)
    session.commit()

    out = get_source(session, source_id)
    if out is not None:
        out["role"] = clean_role
    return out



def unlink_source_from_track(session: Session, track_id: int, source_id: int) -> bool | None:
    track = session.get(LearningTrack, track_id)
    source = session.get(LearningSource, source_id)
    if not track or not source:
        return None

    link = session.exec(
        select(LearningTrackSource).where(
            LearningTrackSource.track_id == track_id,
            LearningTrackSource.source_id == source_id,
        )
    ).first()
    if not link:
        return False

    session.delete(link)
    track.updated_at = datetime.now()
    session.add(track)
    session.commit()
    return True

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
            item = _source_to_dict(source, section_count=_section_count(session, source.id or 0), chunk_count=_chunk_count(session, source.id or 0))
            item["role"] = link.role
            rows.append(item)
    return rows


def get_source_audit(session: Session) -> dict[str, Any]:
    sources = session.exec(select(LearningSource)).all()
    links = session.exec(select(LearningTrackSource)).all()
    sections = session.exec(select(LearningSourceSection)).all()
    chunks = session.exec(select(LearningSourceChunk)).all()

    linked_source_ids = {link.source_id for link in links}
    parsed_sources = [source for source in sources if source.status == "parsed"]
    unlinked_sources = [source for source in sources if source.id not in linked_source_ids]

    return {
        "phase": "B",
        "status": "ready" if sources else "empty",
        "total_sources": len(sources),
        "linked_sources": len(linked_source_ids),
        "unlinked_sources": len(unlinked_sources),
        "parsed_sources": len(parsed_sources),
        "registered_sources": len([source for source in sources if source.status == "registered"]),
        "total_sections": len(sections),
        "total_chunks": len(chunks),
        "source_types": sorted({source.source_type for source in sources}),
        "trust_levels": sorted({source.trust_level for source in sources}),
    }


def delete_source(session: Session, source_id: int) -> bool:
    source = session.get(LearningSource, source_id)
    if not source:
        return False
    session.exec(delete(LearningSourceChunk).where(LearningSourceChunk.source_id == source_id))
    session.exec(delete(LearningSourceSection).where(LearningSourceSection.source_id == source_id))
    session.exec(delete(LearningTrackSource).where(LearningTrackSource.source_id == source_id))
    session.delete(source)
    session.commit()
    return True
