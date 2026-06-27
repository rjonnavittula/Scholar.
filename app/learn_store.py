"""Persistence helpers for Scholar Forge learning tracks.

The API layer should stay thin. This module owns the deterministic DB shape for
tracks -> modules -> nodes. Generation/RAG comes later.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.models import LearningModule, LearningNode, LearningTrack


def _clean_title(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _clean_modules(values: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        title = str(raw or "").strip()
        key = title.lower()
        if title and key not in seen:
            cleaned.append(title)
            seen.add(key)
    return cleaned or ["Overview"]


def _node_to_dict(node: LearningNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "title": node.title,
        "position": node.position,
        "node_type": node.node_type,
        "exp": node.exp,
        "locked": node.locked,
        "completed": node.completed,
        "mastery": node.mastery,
    }


def _module_to_dict(module: LearningModule, nodes: list[LearningNode]) -> dict[str, Any]:
    return {
        "id": module.id,
        "title": module.title,
        "position": module.position,
        "exp": module.exp,
        "locked": module.locked,
        "completed": module.completed,
        "mastery": module.mastery,
        "nodes": [_node_to_dict(n) for n in nodes],
    }


def get_track_tree(session: Session, track_id: int) -> dict[str, Any] | None:
    track = session.get(LearningTrack, track_id)
    if not track:
        return None

    modules = session.exec(
        select(LearningModule)
        .where(LearningModule.track_id == track.id)
        .order_by(LearningModule.position)
    ).all()

    out_modules: list[dict[str, Any]] = []
    for module in modules:
        nodes = session.exec(
            select(LearningNode)
            .where(LearningNode.module_id == module.id)
            .order_by(LearningNode.position)
        ).all()
        out_modules.append(_module_to_dict(module, nodes))

    return {
        "id": track.id,
        "title": track.title,
        "input_type": track.input_type,
        "role": track.role or None,
        "source_hash": track.source_hash,
        "status": track.status,
        "created_at": track.created_at.isoformat(),
        "updated_at": track.updated_at.isoformat(),
        "modules": out_modules,
    }


def list_tracks(session: Session) -> list[dict[str, Any]]:
    tracks = session.exec(select(LearningTrack).order_by(LearningTrack.created_at.desc())).all()
    summaries: list[dict[str, Any]] = []
    for track in tracks:
        modules = session.exec(select(LearningModule).where(LearningModule.track_id == track.id)).all()
        summaries.append({
            "id": track.id,
            "title": track.title,
            "input_type": track.input_type,
            "role": track.role or None,
            "source_hash": track.source_hash,
            "status": track.status,
            "module_count": len(modules),
            "created_at": track.created_at.isoformat(),
            "updated_at": track.updated_at.isoformat(),
        })
    return summaries


def create_track_from_spec(session: Session, spec: dict[str, Any]) -> dict[str, Any]:
    modules = _clean_modules(spec.get("modules"))
    title = _clean_title(spec.get("track_title") or spec.get("title"), "Untitled Track")
    now = datetime.now()

    track = LearningTrack(
        title=title,
        input_type=_clean_title(spec.get("input_type"), "source_text"),
        role=str(spec.get("role") or "").strip(),
        source_hash=str(spec.get("source_hash") or "").strip(),
        status="draft",
        created_at=now,
        updated_at=now,
    )
    session.add(track)
    session.commit()
    session.refresh(track)

    for idx, module_title in enumerate(modules, start=1):
        locked = idx > 1
        module = LearningModule(
            track_id=track.id,
            title=module_title,
            position=idx,
            locked=locked,
        )
        session.add(module)
        session.flush()

        session.add(LearningNode(
            module_id=module.id,
            title=f"{module_title} Overview",
            position=1,
            locked=locked,
        ))

    session.commit()
    return get_track_tree(session, track.id)  # type: ignore[arg-type]
