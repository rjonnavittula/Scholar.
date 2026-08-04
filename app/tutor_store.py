"""CRUD for tutor mode: enabling/disabling a track's tutor and its message log."""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from app.models import LearningTrack, TutorMessage


def _track_tutor_dict(track: LearningTrack) -> dict[str, Any]:
    return {
        "id": track.id,
        "title": track.title,
        "tutor_enabled": track.tutor_enabled,
        "tutor_system_prompt": track.tutor_system_prompt,
    }


def get_tutor_config(session: Session, track_id: int) -> dict[str, Any] | None:
    track = session.get(LearningTrack, track_id)
    return _track_tutor_dict(track) if track else None


def enable_tutor(session: Session, track_id: int, system_prompt: str) -> dict[str, Any] | None:
    track = session.get(LearningTrack, track_id)
    if not track:
        return None
    prompt = (system_prompt or "").strip()
    if not prompt:
        raise ValueError("system_prompt_required")
    track.tutor_enabled = True
    track.tutor_system_prompt = prompt
    session.add(track)
    session.commit()
    session.refresh(track)
    return _track_tutor_dict(track)


def disable_tutor(session: Session, track_id: int) -> dict[str, Any] | None:
    track = session.get(LearningTrack, track_id)
    if not track:
        return None
    track.tutor_enabled = False
    session.add(track)
    session.commit()
    session.refresh(track)
    return _track_tutor_dict(track)


def _message_to_dict(msg: TutorMessage) -> dict[str, Any]:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
    }


def list_messages(session: Session, track_id: int) -> list[dict[str, Any]] | None:
    if not session.get(LearningTrack, track_id):
        return None
    rows = session.exec(
        select(TutorMessage).where(TutorMessage.track_id == track_id).order_by(TutorMessage.created_at)
    ).all()
    return [_message_to_dict(m) for m in rows]


def add_message(session: Session, track_id: int, role: str, content: str) -> dict[str, Any]:
    msg = TutorMessage(track_id=track_id, role=role, content=content)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return _message_to_dict(msg)


def clear_messages(session: Session, track_id: int) -> bool:
    if not session.get(LearningTrack, track_id):
        return False
    session.exec(delete(TutorMessage).where(TutorMessage.track_id == track_id))
    session.commit()
    return True
