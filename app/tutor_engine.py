"""Tutor conversation core — context assembly and the streamed turn.

Phase 1: plain-text streaming. Phase 2 (app/sandbox_client.py) added an
isolated code-execution primitive. Phase 3 wired it in as a `run_python`
tool the model can call mid-reply, in a bounded loop. Phase 4 Part A adds
`define_tool`: the model can author a new tool (name + JSON-schema
parameters + Python code), smoke-test it in the sandbox, and have it
become callable by name for the rest of this turn and future ones on this
track - reusing the same run_python sandbox path, not a new primitive.
Phase 4 Part B adds `render_plot` (visual tutoring, tier 1): matplotlib
code run in the sandbox with capture_media=True, the resulting PNG saved
via app/media_store.py and referenced by URL rather than inlined.
Phase 4 Part C adds visual tutoring tier 2: `render_animation` (Manim,
in a separate heavier sandbox image, capture_video=True) and
`render_interactive` (self-contained HTML/SVG/JS, no sandbox execution at
all - just stored and rendered client-side in a sandboxed iframe).
"""
from __future__ import annotations

import ast
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
# A define-then-use-then-maybe-fix sequence plausibly needs more round
# trips than a single run_python call did (was 3 pre-Phase-4). Each round
# is a full model inference pass (~161s observed on this hardware in
# Phase 3's live test), so this is a real latency tradeoff, not free.
MAX_TOOL_ROUNDS = 5

BASE_TUTOR_TOOLS = [{
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
}, {
    "type": "function",
    "function": {
        "name": "define_tool",
        "description": (
            "Author a new, reusable tool for this conversation: give it a name, a "
            "one-line description, a JSON Schema for its parameters, and Python code "
            "defining a function with that exact name. The function's return value "
            "(any JSON-serializable value) becomes the tool's result when it's later "
            "called. Once defined, call it by name like any other tool - it stays "
            "available for the rest of this conversation and future ones on this "
            "track. Calling define_tool again with the same name replaces it (use "
            "this to fix a bug after seeing an error from calling it)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tool name, e.g. celsius_to_fahrenheit."},
                "description": {"type": "string", "description": "One-line description of what it does."},
                "parameters_schema": {
                    "type": "string",
                    "description": (
                        "JSON Schema (as a string) for the tool's parameters, e.g. "
                        '\'{"type":"object","properties":{"c":{"type":"number"}},"required":["c"]}\'.'
                    ),
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Python code defining a function named exactly like `name`, e.g. "
                        "'def celsius_to_fahrenheit(c):\\n    return c * 9 / 5 + 32'"
                    ),
                },
            },
            "required": ["name", "description", "parameters_schema", "code"],
        },
    },
}, {
    "type": "function",
    "function": {
        "name": "render_plot",
        "description": (
            "Render a matplotlib plot and show it to the learner - use for graphing "
            "a function, visualizing data, or any explanation that's clearer as a "
            "picture than as text. Write normal matplotlib code (e.g. `import "
            "matplotlib.pyplot as plt`, build the plot) and end by calling "
            "plt.savefig('/tmp/output.png') - do not call plt.show(), it won't do "
            "anything in the sandbox."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python + matplotlib code, ending in plt.savefig('/tmp/output.png').",
                },
            },
            "required": ["code"],
        },
    },
}, {
    "type": "function",
    "function": {
        "name": "render_animation",
        "description": (
            "Render a short math/concept animation with Manim and show it to the "
            "learner - use for anything better explained as motion than as a static "
            "picture (a transformation, a proof unfolding, a graph being built up "
            "step by step). Write a Manim Scene subclass: `from manim import *` "
            "then `class <SceneName>(Scene): def construct(self): ...`. Keep it "
            "SHORT (a few seconds of animation) - renders are slow, low-quality, "
            "and capped at ~90s."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "manim_code": {
                    "type": "string",
                    "description": "Full Manim scene source, including the class definition.",
                },
                "scene_name": {
                    "type": "string",
                    "description": "The exact class name of the Scene to render.",
                },
            },
            "required": ["manim_code", "scene_name"],
        },
    },
}, {
    "type": "function",
    "function": {
        "name": "render_interactive",
        "description": (
            "Show the learner a small interactive visual (a diagram, a mini "
            "simulation, a click-to-reveal explanation) as a self-contained HTML "
            "document - inline <style> and <script> only, no external resources or "
            "network requests (it renders in a sandboxed iframe with no network "
            "access and no access to this app's page, cookies, or storage). Use for "
            "something genuinely interactive; for a static picture use render_plot, "
            "for a math animation use render_animation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "html": {
                    "type": "string",
                    "description": "A complete, self-contained HTML document (inline <style>/<script> only).",
                },
            },
            "required": ["html"],
        },
    },
}]


def _tutor_model() -> str:
    return os.getenv("HIVE_TUTOR_MODEL") or DEFAULT_TUTOR_MODEL


def _tools_for_track(session: Session, track_id: int) -> list[dict[str, Any]]:
    """Base tools plus this track's stored dynamic tools, same JSON-schema shape."""
    from app.tutor_store import list_dynamic_tools

    tools = list(BASE_TUTOR_TOOLS)
    for t in list_dynamic_tools(session, track_id):
        try:
            params = json.loads(t["parameters_schema"] or "{}")
        except (TypeError, ValueError):
            params = {"type": "object", "properties": {}}
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"] or f"Dynamically-defined tool: {t['name']}",
                "parameters": params,
            },
        })
    return tools


def _sandbox_result_to_tool(result: Any) -> tuple[str, dict[str, Any]]:
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


def _error_tool_result(message: str) -> tuple[str, dict[str, Any]]:
    return message, {"stdout": "", "stderr": message, "exit_code": 1, "timed_out": False}


def _handle_define_tool(session: Session, track_id: int, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    name = (args.get("name") or "").strip() if isinstance(args, dict) else ""
    description = (args.get("description") or "").strip() if isinstance(args, dict) else ""
    code = (args.get("code") or "") if isinstance(args, dict) else ""
    schema_raw = args.get("parameters_schema") if isinstance(args, dict) else None

    if not name or not name.isidentifier():
        return _error_tool_result(f"error: 'name' must be a valid identifier, got {name!r}")
    if not code.strip():
        return _error_tool_result("error: no code provided")
    try:
        ast.parse(code)
    except SyntaxError as e:
        return _error_tool_result(f"error: code has a syntax error: {e}")

    if isinstance(schema_raw, dict):
        parameters_schema = json.dumps(schema_raw)
    else:
        parameters_schema = schema_raw or "{}"
        try:
            json.loads(parameters_schema)
        except (TypeError, ValueError) as e:
            return _error_tool_result(f"error: parameters_schema is not valid JSON: {e}")

    # Smoke-test only (exec the definition, not a full call - there's no
    # safe way to guess good test arguments). Catches import/syntax
    # mistakes the model's own review missed; a bad *call* still surfaces
    # normally the first time the model actually invokes the new tool,
    # which flows back through this same loop like any other tool error.
    from app.sandbox_client import get_sandbox_provider
    smoke = get_sandbox_provider().run(code, timeout_s=10)
    if smoke.exit_code != 0 or smoke.timed_out:
        content = f"error: smoke test failed - the code didn't load cleanly:\nstderr:\n{smoke.stderr}"
        return content, {"stdout": smoke.stdout, "stderr": smoke.stderr,
                          "exit_code": smoke.exit_code, "timed_out": smoke.timed_out}

    from app.tutor_store import upsert_dynamic_tool
    upsert_dynamic_tool(session, track_id, name, description, code, parameters_schema)
    content = f"tool '{name}' defined and ready to call."
    return content, {"stdout": content, "stderr": "", "exit_code": 0, "timed_out": False}


def _handle_render_plot(track_id: int, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    code = (args.get("code") or "").strip() if isinstance(args, dict) else ""
    if not code:
        return _error_tool_result("error: no code provided")

    from app.sandbox_client import get_sandbox_provider
    result = get_sandbox_provider().run(code, timeout_s=15, capture_media=True)

    if not result.media_base64:
        # ran fine but wrote no image - most likely forgot plt.savefig, or
        # the code errored (already reflected in stderr/exit_code below).
        content, extra = _sandbox_result_to_tool(result)
        if result.exit_code == 0 and not result.timed_out:
            content += "\n(no image was produced - did the code call plt.savefig('/tmp/output.png')?)"
        return content, extra

    import base64

    from app.media_store import save_media
    media_url = save_media(track_id, result.media_kind or "image/png", base64.b64decode(result.media_base64))

    content = f"plot rendered: {media_url}"
    if result.stdout:
        content += f"\nstdout:\n{result.stdout}"
    extra = {
        "stdout": result.stdout, "stderr": result.stderr,
        "exit_code": result.exit_code, "timed_out": result.timed_out,
        "media_url": media_url, "media_kind": result.media_kind,
    }
    return content, extra


def _handle_render_animation(track_id: int, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    code = (args.get("manim_code") or "").strip() if isinstance(args, dict) else ""
    scene_name = (args.get("scene_name") or "").strip() if isinstance(args, dict) else ""
    if not code or not scene_name:
        return _error_tool_result("error: manim_code and scene_name are both required")

    from app.sandbox_client import get_sandbox_provider
    result = get_sandbox_provider().run(code, timeout_s=90, capture_video=True, scene_name=scene_name)

    if not result.media_base64:
        content, extra = _sandbox_result_to_tool(result)
        if result.exit_code == 0 and not result.timed_out:
            content += "\n(no video was produced - check that scene_name matches the Scene class exactly)"
        return content, extra

    import base64

    from app.media_store import save_media
    media_url = save_media(track_id, result.media_kind or "video/mp4", base64.b64decode(result.media_base64))

    content = f"animation rendered: {media_url}"
    if result.stdout:
        content += f"\nstdout:\n{result.stdout}"
    extra = {
        "stdout": result.stdout, "stderr": result.stderr,
        "exit_code": result.exit_code, "timed_out": result.timed_out,
        "media_url": media_url, "media_kind": result.media_kind,
    }
    return content, extra


# generous but bounded - this is a diagram/mini-sim, not a general file host.
MAX_INTERACTIVE_HTML_BYTES = 200_000


def _handle_render_interactive(track_id: int, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    html = (args.get("html") or "") if isinstance(args, dict) else ""
    if not html.strip():
        return _error_tool_result("error: no html provided")
    raw = html.encode("utf-8")
    if len(raw) > MAX_INTERACTIVE_HTML_BYTES:
        return _error_tool_result(f"error: html too large ({len(raw)} bytes, max {MAX_INTERACTIVE_HTML_BYTES})")

    from app.media_store import save_media
    media_url = save_media(track_id, "text/html", raw)
    content = f"interactive visual rendered: {media_url}"
    extra = {"stdout": content, "stderr": "", "exit_code": 0, "timed_out": False,
              "media_url": media_url, "media_kind": "text/html"}
    return content, extra


def _run_tool(session: Session, track_id: int, name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Execute one requested tool call.

    Returns (content_for_the_tool_message, extra_fields_for_the_tool_result_event).
    Never raises - an unknown tool or a sandbox failure becomes an error
    string fed back to the model like any other tool output, not a crashed turn.
    """
    if name == "define_tool":
        return _handle_define_tool(session, track_id, args if isinstance(args, dict) else {})
    if name == "render_plot":
        return _handle_render_plot(track_id, args if isinstance(args, dict) else {})
    if name == "render_animation":
        return _handle_render_animation(track_id, args if isinstance(args, dict) else {})
    if name == "render_interactive":
        return _handle_render_interactive(track_id, args if isinstance(args, dict) else {})

    from app.sandbox_client import get_sandbox_provider

    if name == "run_python":
        code = (args.get("code") or "").strip() if isinstance(args, dict) else ""
        if not code:
            return _error_tool_result("error: no code provided")
        result = get_sandbox_provider().run(code, timeout_s=10)
        return _sandbox_result_to_tool(result)

    from app.tutor_store import get_dynamic_tool
    stored = get_dynamic_tool(session, track_id, name)
    if not stored:
        return _error_tool_result(f"error: unknown tool '{name}'")

    args_dict = args if isinstance(args, dict) else {}
    call_code = stored["code"] + f"\nimport json as __json\nprint(__json.dumps({name}(**{args_dict!r})))"
    result = get_sandbox_provider().run(call_code, timeout_s=10)
    return _sandbox_result_to_tool(result)

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
                # Recomputed each round (not hoisted above the loop): a
                # define_tool call earlier in this same turn must make the
                # new tool callable on the very next round, not just future
                # turns.
                round_tools = _tools_for_track(session, track_id) if use_tools else None
                for chunk in stream_chat(messages, model=model, tools=round_tools):
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
                    content, extra = _run_tool(session, track_id, name, args)
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
