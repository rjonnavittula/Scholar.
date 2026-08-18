"""Ollama chat-generation helpers for Scholar RAG lesson content and the tutor.

This mirrors embedding_client.py's shape: same env-var config pattern, same
never-raise health check. rag_engine.py depends on generate_json; tutor_engine.py
depends on generate_text and stream_chat.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Generator, Iterable

DEFAULT_OLLAMA_URL = "http://10.0.0.160:11434"
DEFAULT_GENERATION_MODEL = "llama3.1"
DEFAULT_TIMEOUT = 180


def generation_config() -> dict[str, Any]:
    """Return runtime Ollama generation config without touching the network."""
    return {
        "url": (os.getenv("HIVE_OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL).rstrip("/"),
        "model": os.getenv("HIVE_GENERATION_MODEL") or DEFAULT_GENERATION_MODEL,
        "timeout": float(os.getenv("HIVE_OLLAMA_GENERATION_TIMEOUT") or DEFAULT_TIMEOUT),
    }


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw or "{}")


def _get_json(url: str, *, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw or "{}")


def get_generation_health() -> dict[str, Any]:
    """Return Ollama chat-generation health for UI/API diagnostics."""
    cfg = generation_config()
    base = {"layer": "generation", "provider": "ollama", "url": cfg["url"], "model": cfg["model"]}
    try:
        tags = _get_json(f"{cfg['url']}/api/tags", timeout=min(cfg["timeout"], 15))
        models = [item.get("name", "") for item in tags.get("models", []) if isinstance(item, dict)]
        model_ready = cfg["model"] in models or any(name.startswith(cfg["model"] + ":") for name in models)
        return {**base, "status": "ready" if model_ready else "missing_model", "model_ready": model_ready, "models": models}
    except Exception as exc:
        return {**base, "status": "unavailable", "model_ready": False, "error": str(exc)}


def generate_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Ask the local Ollama chat model for a JSON object.

    Raises RuntimeError on any network/model/parse failure so callers
    (rag_engine) can fall back instead of crashing the request.
    """
    cfg = generation_config()
    try:
        data = _post_json(
            f"{cfg['url']}/api/chat",
            {
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "format": "json",
                "stream": False,
            },
            timeout=cfg["timeout"],
        )
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    content = (data.get("message") or {}).get("content")
    if not content:
        raise RuntimeError("generation_empty_response")
    try:
        return json.loads(content)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"generation_invalid_json:{exc}") from exc


def generate_text(system_prompt: str, user_prompt: str) -> str:
    """Ask the local Ollama chat model for a plain-text reply (no JSON mode).

    Raises RuntimeError on any network/model failure, same contract as
    generate_json, for callers that want a one-shot non-streaming reply.
    """
    cfg = generation_config()
    try:
        data = _post_json(
            f"{cfg['url']}/api/chat",
            {
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            timeout=cfg["timeout"],
        )
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    content = (data.get("message") or {}).get("content")
    if not content:
        raise RuntimeError("generation_empty_response")
    return content


def stream_chat(messages: list[dict[str, Any]], *, model: str | None = None,
                 tools: list[dict[str, Any]] | None = None) -> Generator[dict[str, Any], None, None]:
    """Stream a multi-turn chat reply from Ollama, yielding raw response chunks.

    Each yielded dict is one parsed NDJSON line from Ollama's streaming
    /api/chat — {"message": {"role": "assistant", "content": "...", "tool_calls": [...]}, "done": bool, ...}.
    Never raises past this boundary: on any connection/parse failure, yields
    a single {"error": "..."} dict and stops, so a broken stream never leaves
    a caller hanging or crashes an in-progress HTTP response.
    """
    cfg = generation_config()
    payload: dict[str, Any] = {
        "model": model or cfg["model"],
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    try:
        req = urllib.request.Request(
            f"{cfg['url']}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except (TypeError, ValueError):
                    continue
    except Exception as exc:
        yield {"error": str(exc)}
