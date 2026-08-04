"""OKF: portable export/import of a Scholar learning track.

A bundle carries the track's module/node/lesson/block tree plus each linked
source's raw body_text. Sections and chunks are deliberately NOT serialized —
they're deterministic derivatives of body_text (same parser/chunker version
in, same rows out), so import regenerates them instead of round-tripping
them byte-for-byte. Qdrant indexing is not triggered on import; that stays a
manual per-source step, same as any freshly added source.
"""
from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session

OKF_VERSION = 1


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(title or "").lower()).strip("-")
    return slug or "course"


def export_track_okf(session: Session, track_id: int) -> dict[str, Any] | None:
    from app.learn_store import get_lesson_for_node, get_track_tree
    from app.source_store import get_source, list_track_sources

    tree = get_track_tree(session, track_id)
    if not tree:
        return None

    modules_out: list[dict[str, Any]] = []
    for module in tree["modules"]:
        nodes_out: list[dict[str, Any]] = []
        for node in module["nodes"]:
            lesson = get_lesson_for_node(session, node["id"])
            nodes_out.append({
                "title": node["title"],
                "position": node["position"],
                "node_type": node["node_type"],
                "exp": node["exp"],
                "lesson": {
                    "title": lesson["title"],
                    "status": lesson["status"],
                    "estimated_min": lesson["estimated_min"],
                    "blocks": [
                        {
                            "block_type": b["block_type"],
                            "title": b["title"],
                            "payload": b["payload"],
                            "source_refs": b["source_refs"],
                            "confidence": b["confidence"],
                        }
                        for b in lesson["blocks"]
                    ],
                } if lesson else None,
            })
        modules_out.append({
            "title": module["title"],
            "position": module["position"],
            "exp": module["exp"],
            "nodes": nodes_out,
        })

    sources_out: list[dict[str, Any]] = []
    for link in list_track_sources(session, track_id) or []:
        source = get_source(session, int(link["id"]))
        if not source or not source.get("body_text"):
            continue
        sources_out.append({
            "title": source["title"],
            "source_type": source["source_type"],
            "trust_level": source["trust_level"],
            "body_text": source["body_text"],
            "role": link.get("role", "primary"),
        })

    return {
        "okf_version": OKF_VERSION,
        "track": {
            "title": tree["title"],
            "input_type": tree["input_type"],
            "role": tree["role"] or "",
        },
        "modules": modules_out,
        "sources": sources_out,
    }


def export_filename(bundle: dict[str, Any]) -> str:
    return f"{_slugify(bundle.get('track', {}).get('title', 'course'))}.okf.json"


def import_track_okf(session: Session, bundle: dict[str, Any]) -> dict[str, Any]:
    from app.chunker import chunk_registered_source
    from app.learn_store import get_or_create_lesson_for_node, get_track_tree, replace_lesson_blocks
    from app.models import LearningModule, LearningNode, LearningTrack
    from app.source_store import create_source, link_source_to_track

    if not isinstance(bundle, dict) or not isinstance(bundle.get("track"), dict):
        raise ValueError("invalid_okf_bundle")

    track_spec = bundle["track"]
    title = str(track_spec.get("title") or "").strip() or "Imported Course"

    track = LearningTrack(
        title=title,
        input_type=str(track_spec.get("input_type") or "source_text"),
        role=str(track_spec.get("role") or ""),
        status="draft",
    )
    session.add(track)
    session.commit()
    session.refresh(track)

    for m_idx, module_spec in enumerate(bundle.get("modules") or [], start=1):
        module = LearningModule(
            track_id=track.id,  # type: ignore[arg-type]
            title=str(module_spec.get("title") or f"Module {m_idx}").strip(),
            position=int(module_spec.get("position") or m_idx),
            exp=int(module_spec.get("exp") or 100),
            locked=m_idx > 1,
        )
        session.add(module)
        session.flush()

        for n_idx, node_spec in enumerate(module_spec.get("nodes") or [], start=1):
            node = LearningNode(
                module_id=module.id,  # type: ignore[arg-type]
                title=str(node_spec.get("title") or f"Node {n_idx}").strip(),
                position=int(node_spec.get("position") or n_idx),
                node_type=str(node_spec.get("node_type") or "lesson"),
                exp=int(node_spec.get("exp") or 50),
                locked=m_idx > 1,
            )
            session.add(node)
            session.flush()

            lesson_spec = node_spec.get("lesson")
            if isinstance(lesson_spec, dict) and lesson_spec.get("blocks"):
                lesson = get_or_create_lesson_for_node(session, node.id)  # type: ignore[arg-type]
                if lesson:
                    replace_lesson_blocks(session, int(lesson["id"]), lesson_spec["blocks"])

    for source_spec in bundle.get("sources") or []:
        if not isinstance(source_spec, dict) or not str(source_spec.get("body_text") or "").strip():
            continue
        source = create_source(session, {
            "title": source_spec.get("title"),
            "source_type": source_spec.get("source_type"),
            "trust_level": source_spec.get("trust_level"),
            "body_text": source_spec.get("body_text"),
        })
        link_source_to_track(session, track.id, int(source["id"]), role=source_spec.get("role") or "primary")  # type: ignore[arg-type]
        try:
            chunk_registered_source(session, int(source["id"]))
        except Exception:
            pass  # a bad/unparseable source shouldn't fail the whole import

    session.commit()
    return {"track": get_track_tree(session, track.id)}  # type: ignore[arg-type]
