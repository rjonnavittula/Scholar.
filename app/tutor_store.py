"""CRUD for tutor mode: enabling/disabling a track's tutor and its message log."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from app.models import LearningTrack, TutorDynamicTool, TutorMessage


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
        "tool_calls_json": msg.tool_calls_json,
        "tool_name": msg.tool_name,
    }


def list_messages(session: Session, track_id: int) -> list[dict[str, Any]] | None:
    if not session.get(LearningTrack, track_id):
        return None
    rows = session.exec(
        select(TutorMessage).where(TutorMessage.track_id == track_id).order_by(TutorMessage.created_at)
    ).all()
    return [_message_to_dict(m) for m in rows]


def add_message(session: Session, track_id: int, role: str, content: str,
                 *, tool_calls_json: str | None = None, tool_name: str | None = None) -> dict[str, Any]:
    msg = TutorMessage(track_id=track_id, role=role, content=content,
                        tool_calls_json=tool_calls_json, tool_name=tool_name)
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


def truncate_after_last_user_message(session: Session, track_id: int) -> str | None:
    """For regenerate: deletes every message after the most recent user
    turn (the tutor's reply and any tool round-trip that produced it), so
    the model can be asked to answer that same turn again. Returns that
    user message's content, or None if there's no user turn to regenerate
    from (empty conversation)."""
    rows = session.exec(
        select(TutorMessage).where(TutorMessage.track_id == track_id).order_by(TutorMessage.created_at)
    ).all()
    last_user_index = next((i for i in range(len(rows) - 1, -1, -1) if rows[i].role == "user"), None)
    if last_user_index is None:
        return None
    for m in rows[last_user_index + 1:]:
        session.delete(m)
    session.commit()
    return rows[last_user_index].content


def _dynamic_tool_to_dict(tool: TutorDynamicTool) -> dict[str, Any]:
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "parameters_schema": tool.parameters_schema,
        "code": tool.code,
    }


def list_dynamic_tools(session: Session, track_id: int) -> list[dict[str, Any]]:
    rows = session.exec(
        select(TutorDynamicTool).where(TutorDynamicTool.track_id == track_id).order_by(TutorDynamicTool.name)
    ).all()
    return [_dynamic_tool_to_dict(t) for t in rows]


def get_dynamic_tool(session: Session, track_id: int, name: str) -> dict[str, Any] | None:
    tool = session.exec(
        select(TutorDynamicTool).where(TutorDynamicTool.track_id == track_id, TutorDynamicTool.name == name)
    ).first()
    return _dynamic_tool_to_dict(tool) if tool else None


def upsert_dynamic_tool(session: Session, track_id: int, name: str, description: str,
                         code: str, parameters_schema: str) -> dict[str, Any]:
    tool = session.exec(
        select(TutorDynamicTool).where(TutorDynamicTool.track_id == track_id, TutorDynamicTool.name == name)
    ).first()
    if tool:
        tool.description = description
        tool.code = code
        tool.parameters_schema = parameters_schema
        tool.updated_at = datetime.now()
    else:
        tool = TutorDynamicTool(track_id=track_id, name=name, description=description,
                                 code=code, parameters_schema=parameters_schema)
    session.add(tool)
    session.commit()
    session.refresh(tool)
    return _dynamic_tool_to_dict(tool)
