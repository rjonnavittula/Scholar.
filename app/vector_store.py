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


def upsert_source_chunks(session: Any, source_id: int) -> dict[str, Any]:
    """Embed and upsert a source's chunks into Qdrant.

    SQL chunk rows remain authoritative; this only pushes vectors plus a thin
    payload for retrieval. A chunk whose hash already matches an indexed
    point is skipped, so re-running this after a partial failure is cheap.
    Never raises for connectivity issues — returns a status dict instead so
    the UI can show a clear message.
    """
    from app.chunk_store import list_source_chunks
    from app.embedding_client import embed_text

    chunks = list_source_chunks(session, source_id)
    if chunks is None:
        raise ValueError("source_not_found")
    if not chunks:
        return {"status": "ready", "indexed": 0, "skipped": 0, "failed": 0}

    cfg = qdrant_config()
    try:
        from qdrant_client.http.models import PointStruct

        client = _client()
        ensure_scholar_collection()

        ids = [chunk["id"] for chunk in chunks]
        existing_hashes: dict[int, str] = {}
        for record in client.retrieve(collection_name=cfg["collection"], ids=ids, with_payload=True):
            payload = record.payload or {}
            existing_hashes[record.id] = payload.get("chunk_hash", "")

        indexed = skipped = failed = 0
        points: list[PointStruct] = []
        for chunk in chunks:
            if chunk["chunk_hash"] and existing_hashes.get(chunk["id"]) == chunk["chunk_hash"]:
                skipped += 1
                continue
            try:
                vector = embed_text(chunk["body_text"])
            except Exception:
                failed += 1
                continue
            points.append(PointStruct(
                id=chunk["id"],
                vector=vector,
                payload={
                    "source_id": chunk["source_id"],
                    "chunk_id": chunk["id"],
                    "heading": chunk["heading"],
                    "heading_path": chunk["heading_path"],
                    "position": chunk["position"],
                    "chunk_hash": chunk["chunk_hash"],
                },
            ))
            indexed += 1

        if points:
            client.upsert(collection_name=cfg["collection"], points=points)
        return {"status": "ready", "indexed": indexed, "skipped": skipped, "failed": failed}
    except Exception as exc:
        return {"status": "unavailable", "indexed": 0, "skipped": 0, "failed": len(chunks), "error": str(exc)}


def search_chunks(query_text: str, source_ids: list[int], top_k: int = 6) -> list[dict[str, Any]]:
    """Semantic search over already-indexed chunks, scoped to given sources.

    Returns [] whenever there is nothing to search, or Qdrant/embeddings are
    unavailable, rather than raising — RAG generation falls back to a
    deterministic chunk order when this comes back empty.
    """
    if not source_ids or not (query_text or "").strip():
        return []
    try:
        from app.embedding_client import embed_text
        from qdrant_client.http.models import FieldCondition, Filter, MatchAny

        vector = embed_text(query_text)
        cfg = qdrant_config()
        client = _client()
        hits = client.search(
            collection_name=cfg["collection"],
            query_vector=vector,
            query_filter=Filter(must=[FieldCondition(key="source_id", match=MatchAny(any=source_ids))]),
            limit=top_k,
        )
        return [
            {
                "chunk_id": (hit.payload or {}).get("chunk_id", hit.id),
                "source_id": (hit.payload or {}).get("source_id"),
                "score": hit.score,
            }
            for hit in hits
        ]
    except Exception:
        return []


def get_memory_layers() -> dict[str, Any]:
    from app.embedding_client import get_embedding_health
    from app.generation_client import get_generation_health

    qdrant = get_qdrant_health()
    embedding = get_embedding_health()
    generation = get_generation_health()
    qdrant_status = qdrant.get("status", "unavailable")
    embedding_status = embedding.get("status", "unavailable")
    generation_status = generation.get("status", "unavailable")
    rag_ready = qdrant_status == "ready" and embedding_status == "ready" and generation_status == "ready"
    return {
        "phase": "E",
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
                "description": "Semantic vector index for Scholar chunks.",
                "details": qdrant,
            },
            {
                "id": "embeddings",
                "label": "Embeddings",
                "status": embedding_status,
                "description": "Ollama embedding layer using nomic-embed-text.",
                "details": embedding,
            },
            {
                "id": "rag",
                "label": "RAG Runtime",
                "status": "ready" if rag_ready else "unavailable",
                "description": "Retrieval pipeline that selects chunks, builds context, and grounds generated lesson blocks.",
                "details": {"generation": generation},
            },
            {
                "id": "okf",
                "label": "OKF Memory Layer",
                "status": "planned",
                "description": "Portable curated memory export/import layer for high-value H.I.V.E. knowledge. Tracked now so we do not forget it.",
            },
        ],
    }
