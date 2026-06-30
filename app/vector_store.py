"""Qdrant vector-memory helpers for Scholar.

Phase D begins here. SQL remains the source of truth; Qdrant is only the
semantic-search index for already stored chunks. OKF is tracked as a planned
portable memory layer, not as the active retrieval index yet.
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_QDRANT_URL = "http://10.0.0.126:6333"
DEFAULT_COLLECTION = "hive_scholar_chunks"
DEFAULT_VECTOR_SIZE = 768
DEFAULT_DISTANCE = "Cosine"


def qdrant_config() -> dict[str, Any]:
    """Return runtime Qdrant settings without opening a network connection."""
    return {
        "url": os.getenv("HIVE_QDRANT_URL") or os.getenv("QDRANT_URL") or DEFAULT_QDRANT_URL,
        "collection": os.getenv("HIVE_QDRANT_COLLECTION") or DEFAULT_COLLECTION,
        "vector_size": int(os.getenv("HIVE_QDRANT_VECTOR_SIZE") or os.getenv("HIVE_EMBEDDING_DIM") or DEFAULT_VECTOR_SIZE),
        "distance": os.getenv("HIVE_QDRANT_DISTANCE") or DEFAULT_DISTANCE,
        "embedding_model": os.getenv("HIVE_EMBEDDING_MODEL") or "nomic-embed-text",
    }


def _client():
    from qdrant_client import QdrantClient

    cfg = qdrant_config()
    return QdrantClient(url=cfg["url"], timeout=5)


def get_qdrant_health() -> dict[str, Any]:
    """Check Qdrant availability and Scholar collection presence.

    This function never raises for normal connectivity/import failures because
    the UI should show a useful memory-layer status instead of crashing Scholar.
    """
    cfg = qdrant_config()
    try:
        client = _client()
        collections = client.get_collections().collections
        names = [item.name for item in collections]
        exists = cfg["collection"] in names
        return {
            "layer": "qdrant",
            "status": "ready" if exists else "missing_collection",
            "url": cfg["url"],
            "collection": cfg["collection"],
            "collection_exists": exists,
            "vector_size": cfg["vector_size"],
            "distance": cfg["distance"],
            "embedding_model": cfg["embedding_model"],
            "collections": names,
        }
    except Exception as exc:  # includes missing package, network, and Qdrant errors
        return {
            "layer": "qdrant",
            "status": "unavailable",
            "url": cfg["url"],
            "collection": cfg["collection"],
            "collection_exists": False,
            "vector_size": cfg["vector_size"],
            "distance": cfg["distance"],
            "embedding_model": cfg["embedding_model"],
            "error": str(exc),
        }


def ensure_scholar_collection(*, recreate: bool = False) -> dict[str, Any]:
    """Create the Scholar chunk collection if Qdrant is reachable.

    The collection stores vectors for LearningSourceChunk rows. Payloads and
    chunk IDs will arrive in later Phase D patches.
    """
    cfg = qdrant_config()
    try:
        from qdrant_client.http.models import Distance, VectorParams

        client = _client()
        names = [item.name for item in client.get_collections().collections]
        exists = cfg["collection"] in names
        if exists and recreate:
            client.delete_collection(collection_name=cfg["collection"])
            exists = False
        if not exists:
            distance = getattr(Distance, str(cfg["distance"]).upper(), Distance.COSINE)
            client.create_collection(
                collection_name=cfg["collection"],
                vectors_config=VectorParams(size=cfg["vector_size"], distance=distance),
            )
        return get_qdrant_health()
    except Exception as exc:
        return {
            "layer": "qdrant",
            "status": "unavailable",
            "url": cfg["url"],
            "collection": cfg["collection"],
            "collection_exists": False,
            "vector_size": cfg["vector_size"],
            "distance": cfg["distance"],
            "embedding_model": cfg["embedding_model"],
            "error": str(exc),
        }


def get_memory_layers() -> dict[str, Any]:
    from app.embedding_client import get_embedding_health

    qdrant = get_qdrant_health()
    embedding = get_embedding_health()
    qdrant_status = qdrant.get("status", "unavailable")
    embedding_status = embedding.get("status", "unavailable")
    return {
        "phase": "D",
        "active_layer": "qdrant",
        "layers": [
            {
                "id": "sql",
                "label": "SQL Canon",
                "status": "ready",
                "description": "Courses, sources, sections, chunks, links, and progress stay authoritative in Postgres.",
            },
            {
                "id": "qdrant",
                "label": "Qdrant Index",
                "status": qdrant_status,
                "description": "Semantic vector index for Scholar chunks. Embeddings/upserts land next.",
                "details": qdrant,
            },
            {
                "id": "embeddings",
                "label": "Embeddings",
                "status": embedding_status,
                "description": "Ollama embedding layer using nomic-embed-text. Chunk upserts land next.",
                "details": embedding,
            },
            {
                "id": "rag",
                "label": "RAG Runtime",
                "status": "planned",
                "description": "Retrieval pipeline that will select chunks, build context, cite sources, and ground lesson answers.",
            },
            {
                "id": "okf",
                "label": "OKF Memory Layer",
                "status": "planned",
                "description": "Portable curated memory export/import layer for high-value H.I.V.E. knowledge. Tracked now so we do not forget it.",
            },
        ],
    }
