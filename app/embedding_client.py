"""Ollama embedding helpers for Scholar memory.

This patch only checks and produces embeddings. Later Phase D patches will use
these vectors to upsert chunks into Qdrant.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_OLLAMA_URL = "http://10.0.0.160:11434"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_EMBED_DIM = 768
DEFAULT_TIMEOUT = 15


def embedding_config() -> dict[str, Any]:
    """Return runtime Ollama embedding config without touching the network."""
    return {
        "url": (os.getenv("HIVE_OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL).rstrip("/"),
        "model": os.getenv("HIVE_EMBEDDING_MODEL") or os.getenv("OLLAMA_EMBEDDING_MODEL") or DEFAULT_EMBED_MODEL,
        "expected_dim": int(os.getenv("HIVE_EMBEDDING_DIM") or DEFAULT_EMBED_DIM),
        "timeout": float(os.getenv("HIVE_OLLAMA_TIMEOUT") or DEFAULT_TIMEOUT),
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


def normalize_embedding_response(data: dict[str, Any]) -> list[float]:
    """Support both Ollama embedding response shapes.

    /api/embeddings returns: {"embedding": [...]}
    /api/embed returns:      {"embeddings": [[...]]}
    """
    if isinstance(data.get("embedding"), list):
        return [float(x) for x in data["embedding"]]
    embeddings = data.get("embeddings")
    if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
        return [float(x) for x in embeddings[0]]
    raise ValueError("embedding_missing")


def embed_text(text: str) -> list[float]:
    """Embed one string through Ollama.

    Raises ValueError for empty input and RuntimeError for network/model issues.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("text_required")
    cfg = embedding_config()
    try:
        data = _post_json(
            f"{cfg['url']}/api/embeddings",
            {"model": cfg["model"], "prompt": cleaned},
            timeout=cfg["timeout"],
        )
        vector = normalize_embedding_response(data)
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    expected = int(cfg["expected_dim"])
    if expected and len(vector) != expected:
        raise RuntimeError(f"embedding_dim_mismatch:{len(vector)}!=expected:{expected}")
    return vector


def get_embedding_health() -> dict[str, Any]:
    """Return Ollama embedding-layer health for UI/API diagnostics."""
    cfg = embedding_config()
    base = {
        "layer": "embeddings",
        "provider": "ollama",
        "url": cfg["url"],
        "model": cfg["model"],
        "expected_dim": cfg["expected_dim"],
    }
    try:
        tags = _get_json(f"{cfg['url']}/api/tags", timeout=cfg["timeout"])
        models = [item.get("name", "") for item in tags.get("models", []) if isinstance(item, dict)]
        model_ready = cfg["model"] in models or any(name.startswith(cfg["model"] + ":") for name in models)
        return {
            **base,
            "status": "ready" if model_ready else "missing_model",
            "model_ready": model_ready,
            "models": models,
        }
    except Exception as exc:
        return {
            **base,
            "status": "unavailable",
            "model_ready": False,
            "error": str(exc),
        }


def embed_text_preview(text: str) -> dict[str, Any]:
    """Embed text and return diagnostics without dumping the full vector."""
    vector = embed_text(text)
    preview = vector[:5]
    return {
        "provider": "ollama",
        "model": embedding_config()["model"],
        "dimension": len(vector),
        "preview": preview,
        "vector_checksum": round(sum(vector), 6),
    }
