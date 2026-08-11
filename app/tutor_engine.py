"""Tutor conversation core — context assembly and the streamed turn.

Phase 1: plain-text streaming. Phase 2 (app/sandbox_client.py) added an
isolated code-execution primitive, unused until now. Phase 3 (this file)
wires it in as a `run_python` tool the model can call mid-reply, in a
bounded loop. Dynamic tool authoring (Phase 4) is a separate, larger
feature and still out of scope here.
"""
from __future__ import annotations

import json
import os
from typing import Any, Generator

from sqlmodel import Session

# qwen3:4b, not the app's general chat default - the tutor specifically
# needs a model that's actually reliable at tool-calling (confirmed via
# this session's own research: llama3.1, the general default, isn't).
# Independent of HIVE_GENERATION_MODEL on purpose, so changing the general
# default elsewhere can't silently regress the tutor's tool-calling.
DEFAULT_TUTOR_MODEL = "qwen3:4b"
MAX_TOOL_ROUNDS = 3

TUTOR_TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Execute a short Python snippet in an isolated sandbox (no network, "
            "~10s limit) and return its stdout/stderr. Use to verify a calculation, "
            "test code you're explaining, or demonstrate a concept concretely - "
            "not for anything that needs external data."
        ),
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "The Python code to run."}},
            "required": ["code"],
        },
    },
}]


def _tutor_model() -> str:
    return os.getenv("HIVE_TUTOR_MODEL") or DEFAULT_TUTOR_MODEL


def _run_tool(name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Execute one requested tool call.

    Returns (content_for_the_tool_message, extra_fields_for_the_tool_result_event).
    Never raises - an unknown tool or a sandbox failure becomes an error
    string fed back to the model like any other tool output, not a crashed turn.
    """
    if name != "run_python":
        content = f"error: unknown tool '{name}'"
        return content, {"stdout": "", "stderr": content, "exit_code": 1, "timed_out": False}

    code = (args.get("code") or "").strip() if isinstance(args, dict) else ""
    if not code:
        content = "error: no code provided"
        return content, {"stdout": "", "stderr": content, "exit_code": 1, "timed_out": False}

    from app.sandbox_client import get_sandbox_provider
    result = get_sandbox_provider().run(code, timeout_s=10)
    parts = []
    if result.stdout:
        parts.append(f"stdout:\n{result.stdout}")
    if result.stderr:
        parts.append(f"stderr:\n{result.stderr}")
    parts.append(f"exit_code: {result.exit_code}" + (" (timed out)" if result.timed_out else ""))
    content = "\n".join(parts)
    extra = {"stdout": result.stdout, "stderr": result.stderr,
              "exit_code": result.exit_code, "timed_out": result.timed_out}
    return content, extra

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
            entry: dict[str, Any] = {"role": m["role"], "content": m["content"]}
            if m["role"] == "assistant" and m.get("tool_calls_json"):
                try:
                    entry["tool_calls"] = json.loads(m["tool_calls_json"])
                except (TypeError, ValueError):
                    pass
            messages.append(entry)
        elif m["role"] == "tool":
            messages.append({"role": "tool", "content": m["content"]})

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

    A bounded loop (MAX_TOOL_ROUNDS), not a single stream_chat call: if the
    model asks to call run_python, run it, feed the result back, and let the
    model continue - up to the round cap, which forces a final tools-off
    round so a turn always ends in a text reply instead of hanging.

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
        model = _tutor_model()

        # Tracks the in-progress round's text so a client disconnecting
        # mid-stream (GeneratorExit) still gets its partial reply persisted,
        # same guarantee the old single-round version had via try/finally -
        # `persisted` is reset each round and flipped True by whichever
        # normal-path add_message() already saved this round's full_reply,
        # so the finally block only ever fires as a fallback, never a dup.
        full_reply = ""
        tool_calls: list[dict[str, Any]] | None = None
        persisted = False
        try:
            for round_num in range(MAX_TOOL_ROUNDS + 1):
                full_reply = ""
                tool_calls = None
                persisted = False
                use_tools = round_num < MAX_TOOL_ROUNDS
                for chunk in stream_chat(messages, model=model, tools=TUTOR_TOOLS if use_tools else None):
                    if chunk.get("error"):
                        yield {"type": "error", "content": chunk["error"]}
                        return
                    msg = chunk.get("message") or {}
                    content = msg.get("content") or ""
                    if content:
                        full_reply += content
                        yield {"type": "text_delta", "content": content}
                    if msg.get("tool_calls"):
                        tool_calls = msg["tool_calls"]
                    if chunk.get("done"):
                        break

                if not tool_calls:
                    if full_reply.strip():
                        add_message(session, track_id, "assistant", full_reply)
                        persisted = True
                    return

                # the model wants to use a tool: persist the request (content
                # may be empty - some models emit a tool call with no visible
                # text), run each requested call, persist + feed back its
                # result, and loop so the model can react to what it learned.
                add_message(session, track_id, "assistant", full_reply, tool_calls_json=json.dumps(tool_calls))
                persisted = True
                messages.append({"role": "assistant", "content": full_reply, "tool_calls": tool_calls})

                for call in tool_calls:
                    fn = call.get("function") or {}
                    name = fn.get("name") or ""
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (TypeError, ValueError):
                            args = {}
                    yield {"type": "tool_call", "name": name, "args": args}
                    content, extra = _run_tool(name, args)
                    yield {"type": "tool_result", "name": name, "code": args.get("code", ""), **extra}
                    add_message(session, track_id, "tool", content, tool_name=name)
                    messages.append({"role": "tool", "content": content})

            # MAX_TOOL_ROUNDS exhausted without a final text reply - degrade
            # gracefully instead of leaving the stream hanging with no answer.
            fallback = "Stopped after several tool calls without reaching a final answer — try rephrasing?"
            yield {"type": "text_delta", "content": fallback}
            add_message(session, track_id, "assistant", fallback)
            persisted = True
        finally:
            if not persisted and full_reply.strip():
                add_message(session, track_id, "assistant", full_reply)
