"""Persistence helpers for Scholar Forge learning tracks.

The API layer should stay thin. This module owns the deterministic DB shape for
tracks -> modules -> nodes. Generation/RAG comes later.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.models import (
    LearningBlock, LearningLesson, LearningModule, LearningNode, LearningTrack, LearningTrackSource,
    TutorDynamicTool, TutorMessage,
)


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


def _track_summary(session: Session, track: LearningTrack) -> dict[str, Any]:
    modules = session.exec(
        select(LearningModule)
        .where(LearningModule.track_id == track.id)
        .order_by(LearningModule.position)
    ).all()
    return {
        "id": track.id,
        "title": track.title,
        "input_type": track.input_type,
        "role": track.role or None,
        "source_hash": track.source_hash,
        "status": track.status,
        "tutor_enabled": track.tutor_enabled,
        **_progress_from_modules(modules),
        "module_titles": [module.title for module in modules[:4]],
        "created_at": track.created_at.isoformat(),
        "updated_at": track.updated_at.isoformat(),
    }


def _track_dedupe_key(summary: dict[str, Any]) -> str:
    source_hash = str(summary.get("source_hash") or "").strip()
    if source_hash:
        return f"source:{source_hash}"
    modules = "|".join(str(v).strip().lower() for v in summary.get("module_titles") or [])
    return f"title:{str(summary.get('title') or '').strip().lower()}::{modules}"


def _find_existing_track(session: Session, title: str, modules: list[str], source_hash: str) -> LearningTrack | None:
    if source_hash:
        existing = session.exec(
            select(LearningTrack)
            .where(LearningTrack.source_hash == source_hash)
            .order_by(LearningTrack.created_at.desc())
        ).first()
        if existing:
            return existing

    title_key = title.strip().lower()
    candidates = session.exec(
        select(LearningTrack)
        .where(func.lower(LearningTrack.title) == title_key)
        .order_by(LearningTrack.created_at.desc())
    ).all()
    module_key = [m.strip().lower() for m in modules]
    for candidate in candidates:
        candidate_modules = session.exec(
            select(LearningModule)
            .where(LearningModule.track_id == candidate.id)
            .order_by(LearningModule.position)
        ).all()
        if [m.title.strip().lower() for m in candidate_modules] == module_key:
            return candidate
    return None


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
        "tutor_enabled": track.tutor_enabled,
        "tutor_system_prompt": track.tutor_system_prompt,
        **_progress_from_modules(modules),
        "created_at": track.created_at.isoformat(),
        "updated_at": track.updated_at.isoformat(),
        "modules": out_modules,
    }


def list_tracks(session: Session) -> list[dict[str, Any]]:
    tracks = session.exec(select(LearningTrack).order_by(LearningTrack.created_at.desc())).all()
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for track in tracks:
        summary = _track_summary(session, track)
        key = _track_dedupe_key(summary)
        if key in seen:
            continue
        seen.add(key)
        summaries.append(summary)
    return summaries


def create_track_from_spec(session: Session, spec: dict[str, Any]) -> dict[str, Any]:
    modules = _clean_modules(spec.get("modules"))
    title = _clean_title(spec.get("track_title") or spec.get("title"), "Untitled Track")
    source_hash = str(spec.get("source_hash") or "").strip()
    existing = _find_existing_track(session, title, modules, source_hash)
    if existing:
        tree = get_track_tree(session, existing.id)
        if tree is not None:
            tree["deduplicated"] = True
            return tree

    now = datetime.now()

    track = LearningTrack(
        title=title,
        input_type=_clean_title(spec.get("input_type"), "source_text"),
        role=str(spec.get("role") or "").strip(),
        source_hash=source_hash,
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


def _clamp_mastery(value: object) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = 1.0
    return max(0.0, min(1.0, num))


def _module_nodes(session: Session, module_id: int) -> list[LearningNode]:
    return session.exec(
        select(LearningNode)
        .where(LearningNode.module_id == module_id)
        .order_by(LearningNode.position)
    ).all()


def _track_modules(session: Session, track_id: int) -> list[LearningModule]:
    return session.exec(
        select(LearningModule)
        .where(LearningModule.track_id == track_id)
        .order_by(LearningModule.position)
    ).all()


def _progress_from_modules(modules: list[LearningModule]) -> dict[str, Any]:
    module_count = len(modules)
    completed_count = sum(1 for module in modules if module.completed)
    mastery = round(sum(float(module.mastery or 0.0) for module in modules) / module_count, 3) if module_count else 0.0
    next_module = next((module for module in modules if not module.completed and not module.locked), None)
    return {
        "mastery": mastery,
        "module_count": module_count,
        "completed_module_count": completed_count,
        "next_module_title": next_module.title if next_module else None,
    }


def delete_track(session: Session, track_id: int) -> bool:
    track = session.get(LearningTrack, track_id)
    if not track:
        return False

    modules = _track_modules(session, track_id)
    module_ids = [module.id for module in modules if module.id is not None]
    node_ids: list[int] = []
    lesson_ids: list[int] = []

    for module_id in module_ids:
        node_ids.extend(node.id for node in _module_nodes(session, module_id) if node.id is not None)

    if node_ids:
        lessons = session.exec(
            select(LearningLesson).where(LearningLesson.node_id.in_(node_ids))
        ).all()
        lesson_ids = [lesson.id for lesson in lessons if lesson.id is not None]

    if lesson_ids:
        session.exec(delete(LearningBlock).where(LearningBlock.lesson_id.in_(lesson_ids)))
        session.exec(delete(LearningLesson).where(LearningLesson.id.in_(lesson_ids)))

    if node_ids:
        session.exec(delete(LearningNode).where(LearningNode.id.in_(node_ids)))

    if module_ids:
        session.exec(delete(LearningModule).where(LearningModule.id.in_(module_ids)))

    session.exec(delete(LearningTrackSource).where(LearningTrackSource.track_id == track_id))
    session.exec(delete(TutorMessage).where(TutorMessage.track_id == track_id))
    session.exec(delete(TutorDynamicTool).where(TutorDynamicTool.track_id == track_id))

    session.delete(track)
    session.commit()

    from app.media_store import delete_media_for_track
    delete_media_for_track(track_id)
    return True


def _add_starter_blocks(session: Session, lesson: LearningLesson, node: LearningNode) -> None:
    existing = session.exec(
        select(LearningBlock).where(LearningBlock.lesson_id == lesson.id)
    ).all()
    if existing:
        return

    starter_blocks = [
        {
            "block_type": "text",
            "title": "Mission brief",
            "payload": {
                "body": f"Start here. This draft lesson introduces {node.title}. Source-grounded explanations, examples, and checks come next."
            },
        },
        {
            "block_type": "recall_prompt",
            "title": "Recall before reveal",
            "payload": {
                "prompt": f"Before studying, write what you already know about {node.title}."
            },
        },
    ]
    for idx, block in enumerate(starter_blocks, start=1):
        session.add(LearningBlock(
            lesson_id=lesson.id,  # type: ignore[arg-type]
            position=idx,
            block_type=block["block_type"],
            title=block["title"],
            payload_json=_json_dump(block.get("payload"), {}),
            source_refs_json="[]",
            confidence=0.0,
        ))


def _lesson_model_for_node(session: Session, node: LearningNode) -> LearningLesson:
    lesson = session.exec(
        select(LearningLesson).where(LearningLesson.node_id == node.id)
    ).first()
    if lesson:
        _add_starter_blocks(session, lesson, node)
        session.commit()
        return lesson

    now = datetime.now()
    lesson = LearningLesson(
        node_id=node.id,  # type: ignore[arg-type]
        title=node.title,
        status="draft",
        estimated_min=10,
        created_at=now,
        updated_at=now,
    )
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    _add_starter_blocks(session, lesson, node)
    session.commit()
    return lesson


def _recalculate_module(session: Session, module: LearningModule) -> None:
    nodes = _module_nodes(session, module.id)  # type: ignore[arg-type]
    if not nodes:
        module.mastery = 0.0
        module.completed = False
    else:
        module.mastery = round(sum(float(n.mastery or 0.0) for n in nodes) / len(nodes), 3)
        module.completed = all(bool(n.completed) for n in nodes)
    session.add(module)


def _recalculate_track(session: Session, track: LearningTrack) -> None:
    modules = _track_modules(session, track.id)  # type: ignore[arg-type]
    if modules and all(m.completed for m in modules):
        track.status = "completed"
    elif any(m.mastery > 0 or m.completed for m in modules):
        track.status = "active"
    elif track.status == "draft":
        track.status = "active"
    track.updated_at = datetime.now()
    session.add(track)


def _unlock_next_module(session: Session, module: LearningModule) -> None:
    next_module = session.exec(
        select(LearningModule)
        .where(LearningModule.track_id == module.track_id, LearningModule.position > module.position)
        .order_by(LearningModule.position)
    ).first()
    if not next_module:
        return
    next_module.locked = False
    session.add(next_module)
    for node in _module_nodes(session, next_module.id):  # type: ignore[arg-type]
        node.locked = False
        session.add(node)


def start_learning_node(session: Session, node_id: int) -> dict[str, Any] | None:
    node = session.get(LearningNode, node_id)
    if not node:
        return None
    if node.locked:
        raise ValueError("node_locked")

    module = session.get(LearningModule, node.module_id)
    if not module:
        return None
    if module.locked:
        raise ValueError("module_locked")

    track = session.get(LearningTrack, module.track_id)
    if not track:
        return None

    lesson = _lesson_model_for_node(session, node)
    if lesson.status != "completed":
        lesson.status = "in_progress"
        lesson.updated_at = datetime.now()
        session.add(lesson)

    track.status = "active"
    track.updated_at = datetime.now()
    session.add(track)
    session.commit()
    return {"track": get_track_tree(session, track.id), "lesson": get_lesson_tree(session, lesson.id)}  # type: ignore[arg-type]


def complete_learning_node(session: Session, node_id: int, mastery: float = 1.0) -> dict[str, Any] | None:
    node = session.get(LearningNode, node_id)
    if not node:
        return None
    if node.locked:
        raise ValueError("node_locked")

    module = session.get(LearningModule, node.module_id)
    if not module:
        return None
    if module.locked:
        raise ValueError("module_locked")

    track = session.get(LearningTrack, module.track_id)
    if not track:
        return None

    lesson = _lesson_model_for_node(session, node)
    now = datetime.now()
    node.completed = True
    node.mastery = _clamp_mastery(mastery)
    session.add(node)

    lesson.status = "completed"
    lesson.updated_at = now
    session.add(lesson)

    _recalculate_module(session, module)
    if module.completed:
        _unlock_next_module(session, module)
    _recalculate_track(session, track)
    session.commit()

    return {"track": get_track_tree(session, track.id), "lesson": get_lesson_tree(session, lesson.id)}  # type: ignore[arg-type]


ALLOWED_BLOCK_TYPES = {
    "text",
    "definition",
    "recall_prompt",
    "quiz",
    "ordered_relation",
    "case",
    "source_quote",
    "diagram",
    "code",
}


def _json_dump(value: Any, fallback: Any) -> str:
    try:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False)
    except TypeError:
        return json.dumps(fallback, ensure_ascii=False)


def _json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _block_to_dict(block: LearningBlock) -> dict[str, Any]:
    return {
        "id": block.id,
        "position": block.position,
        "block_type": block.block_type,
        "title": block.title,
        "payload": _json_load(block.payload_json, {}),
        "source_refs": _json_load(block.source_refs_json, []),
        "confidence": block.confidence,
    }


def get_lesson_tree(session: Session, lesson_id: int) -> dict[str, Any] | None:
    lesson = session.get(LearningLesson, lesson_id)
    if not lesson:
        return None
    blocks = session.exec(
        select(LearningBlock)
        .where(LearningBlock.lesson_id == lesson.id)
        .order_by(LearningBlock.position)
    ).all()
    return {
        "id": lesson.id,
        "node_id": lesson.node_id,
        "title": lesson.title,
        "status": lesson.status,
        "estimated_min": lesson.estimated_min,
        "created_at": lesson.created_at.isoformat(),
        "updated_at": lesson.updated_at.isoformat(),
        "blocks": [_block_to_dict(b) for b in blocks],
    }


def get_lesson_for_node(session: Session, node_id: int) -> dict[str, Any] | None:
    """Read-only lookup — unlike get_or_create_lesson_for_node, never creates a lesson."""
    lesson = session.exec(select(LearningLesson).where(LearningLesson.node_id == node_id)).first()
    return get_lesson_tree(session, lesson.id) if lesson else None  # type: ignore[arg-type]


def get_or_create_lesson_for_node(session: Session, node_id: int) -> dict[str, Any] | None:
    node = session.get(LearningNode, node_id)
    if not node:
        return None

    lesson = session.exec(
        select(LearningLesson).where(LearningLesson.node_id == node.id)
    ).first()
    if lesson:
        return get_lesson_tree(session, lesson.id)  # type: ignore[arg-type]

    now = datetime.now()
    lesson = LearningLesson(
        node_id=node.id,  # type: ignore[arg-type]
        title=node.title,
        status="draft",
        estimated_min=10,
        created_at=now,
        updated_at=now,
    )
    session.add(lesson)
    session.commit()
    session.refresh(lesson)

    _add_starter_blocks(session, lesson, node)
    session.commit()
    return get_lesson_tree(session, lesson.id)  # type: ignore[arg-type]


def add_lesson_block(session: Session, lesson_id: int, spec: dict[str, Any]) -> dict[str, Any] | None:
    lesson = session.get(LearningLesson, lesson_id)
    if not lesson:
        return None

    block_type = str(spec.get("block_type") or "text").strip()
    if block_type not in ALLOWED_BLOCK_TYPES:
        raise ValueError("invalid_block_type")

    existing = session.exec(select(LearningBlock).where(LearningBlock.lesson_id == lesson.id)).all()
    block = LearningBlock(
        lesson_id=lesson.id,  # type: ignore[arg-type]
        position=len(existing) + 1,
        block_type=block_type,
        title=str(spec.get("title") or "").strip(),
        payload_json=_json_dump(spec.get("payload"), {}),
        source_refs_json=_json_dump(spec.get("source_refs"), []),
        confidence=float(spec.get("confidence") or 0.0),
    )
    session.add(block)
    lesson.updated_at = datetime.now()
    session.add(lesson)
    session.commit()
    return get_lesson_tree(session, lesson.id)  # type: ignore[arg-type]


def replace_lesson_blocks(session: Session, lesson_id: int, blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Swap a lesson's blocks for a freshly generated set.

    Used by RAG generation once a response has been validated against
    ALLOWED_BLOCK_TYPES. Marks the lesson "generated" so the UI can tell it
    apart from the untouched starter-block draft.
    """
    lesson = session.get(LearningLesson, lesson_id)
    if not lesson:
        return None

    session.exec(delete(LearningBlock).where(LearningBlock.lesson_id == lesson.id))
    for position, block in enumerate(blocks, start=1):
        block_type = str(block.get("block_type") or "text").strip()
        if block_type not in ALLOWED_BLOCK_TYPES:
            raise ValueError("invalid_block_type")
        session.add(LearningBlock(
            lesson_id=lesson.id,  # type: ignore[arg-type]
            position=position,
            block_type=block_type,
            title=str(block.get("title") or "").strip(),
            payload_json=_json_dump(block.get("payload"), {}),
            source_refs_json=_json_dump(block.get("source_refs"), []),
            confidence=float(block.get("confidence") or 0.0),
        ))

    lesson.status = "generated"
    lesson.updated_at = datetime.now()
    session.add(lesson)
    session.commit()
    return get_lesson_tree(session, lesson.id)  # type: ignore[arg-type]
