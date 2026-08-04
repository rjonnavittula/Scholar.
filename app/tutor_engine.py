"""Phase 1: tutor conversation core — context assembly and the streamed turn.

Tool-calling (Phase 3) and dynamic tool authoring (Phase 4) extend
run_tutor_turn later; this module only streams plain text replies for now.
"""
from __future__ import annotations

from typing import Any, Generator

from sqlmodel import Session

PROMPT_GEN_SYSTEM = (
    "You write tutor system prompts for a self-hosted study app. Given a short "
    "description of the kind of tutor someone wants, write a complete, ready-to-use "
    "system prompt: persona and tone, how it should teach (its loop — motivate, "
    "explain, have the learner try it, review, test understanding), and any hard "
    "rules it should follow. Write only the system prompt itself, no preamble, no "
    "markdown headers, no commentary about what you wrote."
)


def generate_tutor_prompt(description: str) -> str:
    """Expand a short freeform description into a full tutor system prompt.

    Raises RuntimeError on failure (mirrors generate_json/generate_text) —
    the caller decides how to surface that, this never silently returns junk.
    """
    from app.generation_client import generate_text

    description = (description or "").strip()
    if not description:
        raise ValueError("description_required")
    return generate_text(PROMPT_GEN_SYSTEM, description).strip()


def build_chat_messages(session: Session, track_id: int, user_message: str) -> list[dict[str, Any]] | None:
    from app.rag_engine import search_track
    from app.tutor_store import get_tutor_config, list_messages

    config = get_tutor_config(session, track_id)
    if not config:
        return None

    messages: list[dict[str, Any]] = [{"role": "system", "content": config["tutor_system_prompt"]}]
    for m in list_messages(session, track_id) or []:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"]})

    hits = search_track(session, track_id, user_message, top_k=4)
    if hits:
        excerpts = "\n\n".join(
            f"[{h['source_title'] or 'source'} — {h['heading'] or 'untitled'}]\n{h['snippet']}"
            for h in hits
        )
        messages.append({
            "role": "system",
            "content": (
                "Relevant excerpts from the learner's linked course material, for this turn only "
                "(use if helpful, ignore if not relevant to what they're asking):\n\n" + excerpts
            ),
        })

    messages.append({"role": "user", "content": user_message})
    return messages


def run_tutor_turn(track_id: int, user_message: str) -> Generator[dict[str, Any], None, None]:
    """Persist the user's message, stream the tutor's reply, persist that too.

    Opens its own Session — this generator's body keeps running after the
    FastAPI route handler returns (StreamingResponse), by which point a
    Depends(get_session) session would already be closed. app/main.py's
    _maybe_autosync does the same thing for the same reason.
    """
    from sqlmodel import Session as _Session

    from app.db import engine
    from app.generation_client import stream_chat
    from app.tutor_store import add_message, get_tutor_config

    with _Session(engine) as session:
        config = get_tutor_config(session, track_id)
        if not config or not config["tutor_enabled"]:
            yield {"type": "error", "content": "tutor_not_enabled"}
            return

        add_message(session, track_id, "user", user_message)
        messages = build_chat_messages(session, track_id, user_message)

        full_reply = ""
        try:
            for chunk in stream_chat(messages):
                if chunk.get("error"):
                    yield {"type": "error", "content": chunk["error"]}
                    return
                content = (chunk.get("message") or {}).get("content") or ""
                if content:
                    full_reply += content
                    yield {"type": "text_delta", "content": content}
                if chunk.get("done"):
                    break
        finally:
            if full_reply.strip():
                add_message(session, track_id, "assistant", full_reply)
