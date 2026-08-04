"""Phase E: retrieval-grounded lesson generation for Scholar.

Chunks stay authoritative in Postgres; this module only selects which chunks
back a lesson and turns them into safe LearningBlock payloads via the local
Ollama chat model. Generation failures never raise past the API boundary —
the existing starter-block lesson stays in place and a status is returned.
"""
from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.models import LearningModule, LearningNode, LearningTrack


def gather_context(session: Session, node: LearningNode) -> dict[str, Any]:
    """Pick the chunks a lesson for this node should be grounded in.

    Prefers Qdrant semantic search over the node's linked sources; falls
    back to the first few chunks of each linked source (in order) when
    Qdrant/embeddings are unavailable or return nothing.
    """
    from app.chunk_store import list_source_chunks
    from app.source_store import list_track_sources
    from app.vector_store import search_chunks

    module = session.get(LearningModule, node.module_id)
    track = session.get(LearningTrack, module.track_id) if module else None
    if not track:
        return {"chunks": [], "track": track, "module": module}

    linked = list_track_sources(session, track.id) or []  # type: ignore[arg-type]
    source_ids = [int(item["id"]) for item in linked]
    if not source_ids:
        return {"chunks": [], "track": track, "module": module}

    chunk_by_id: dict[int, dict[str, Any]] = {}
    chunks_by_source: dict[int, list[dict[str, Any]]] = {}
    for source_id in source_ids:
        rows = list_source_chunks(session, source_id) or []
        chunks_by_source[source_id] = rows
        for chunk in rows:
            chunk_by_id[chunk["id"]] = chunk

    query = " — ".join(part for part in (track.title, module.title if module else "", node.title) if part)
    hits = search_chunks(query, source_ids, top_k=8)

    ordered: list[dict[str, Any]] = []
    if hits:
        for hit in hits:
            chunk = chunk_by_id.get(hit.get("chunk_id"))
            if chunk:
                ordered.append(chunk)
    if not ordered:
        for source_id in source_ids:
            ordered.extend(chunks_by_source.get(source_id, [])[:4])

    return {"chunks": ordered[:8], "track": track, "module": module}


def search_track(session: Session, track_id: int, query: str, top_k: int = 10) -> list[dict[str, Any]]:
    """Semantic search over a track's indexed chunks, for direct learner use.

    Returns [] whenever there's nothing to search or Qdrant/embeddings are
    unavailable — same no-raise contract as search_chunks itself.
    """
    from app.chunk_store import list_source_chunks
    from app.source_store import list_track_sources
    from app.vector_store import search_chunks

    if not (query or "").strip():
        return []

    linked = list_track_sources(session, track_id) or []
    source_ids = [int(item["id"]) for item in linked]
    if not source_ids:
        return []
    source_title_by_id = {int(item["id"]): item["title"] for item in linked}

    chunk_by_id: dict[int, dict[str, Any]] = {}
    for source_id in source_ids:
        for chunk in list_source_chunks(session, source_id) or []:
            chunk_by_id[chunk["id"]] = chunk

    hits = search_chunks(query, source_ids, top_k=top_k)
    results: list[dict[str, Any]] = []
    for hit in hits:
        chunk = chunk_by_id.get(hit.get("chunk_id"))
        if not chunk:
            continue
        results.append({
            "chunk_id": chunk["id"],
            "source_id": chunk["source_id"],
            "source_title": source_title_by_id.get(chunk["source_id"], ""),
            "heading": chunk["heading"],
            "snippet": chunk["body_text"][:280],
            "score": hit.get("score"),
        })
    return results


def _validate_blocks(raw_blocks: Any, topic: str) -> list[dict[str, Any]]:
    from app.learn_store import ALLOWED_BLOCK_TYPES

    if not isinstance(raw_blocks, list):
        return []

    cleaned: list[dict[str, Any]] = []
    has_recall = False
    for item in raw_blocks:
        if len(cleaned) >= 6:
            break
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("block_type") or "").strip()
        if block_type not in ALLOWED_BLOCK_TYPES:
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if block_type == "quiz":
            options = payload.get("options")
            correct = payload.get("correct_index")
            if not isinstance(options, list) or len(options) < 2:
                continue
            if not isinstance(correct, int) or not (0 <= correct < len(options)):
                continue
        if block_type == "ordered_relation":
            items = payload.get("items")
            if not isinstance(items, list) or len(items) < 2:
                continue

        confidence_raw = item.get("confidence")
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.0
        cleaned.append({
            "block_type": block_type,
            "title": str(item.get("title") or "").strip(),
            "payload": payload,
            "source_refs": item.get("source_refs") if isinstance(item.get("source_refs"), list) else [],
            "confidence": confidence,
        })
        if block_type == "recall_prompt":
            has_recall = True

    if cleaned and not has_recall:
        cleaned.append({
            "block_type": "recall_prompt",
            "title": "Recall before reveal",
            "payload": {"prompt": f"Before moving on, write what you remember about {topic}."},
            "source_refs": [],
            "confidence": 0.0,
        })
    return cleaned


def generate_lesson_blocks(session: Session, node_id: int) -> dict[str, Any] | None:
    """Generate and save grounded lesson blocks for a node.

    Returns None only when the node itself doesn't exist. Every other
    failure mode (no linked sources, Ollama unavailable, bad JSON, no valid
    blocks) returns the existing lesson untouched with a `generation` status
    the UI can show instead of raising.
    """
    from app.generation_client import generate_json
    from app.learn_store import ALLOWED_BLOCK_TYPES, get_or_create_lesson_for_node, replace_lesson_blocks

    node = session.get(LearningNode, node_id)
    if not node:
        return None

    lesson = get_or_create_lesson_for_node(session, node_id)
    context = gather_context(session, node)
    chunks = context["chunks"]
    if not chunks:
        return {
            "lesson": lesson,
            "generation": {
                "status": "no_sources",
                "message": "Attach a source to this course before generating a grounded lesson.",
            },
        }

    excerpts = "\n\n".join(
        f"[chunk {chunk['id']}] {chunk['heading'] or 'Untitled section'}\n{chunk['body_text'][:900]}"
        for chunk in chunks
    )
    system_prompt = (
        "You are Scholar's lesson author. Write a short study lesson using ONLY the "
        "provided source excerpts — never invent facts outside them. Respond with a "
        'JSON object shaped {"blocks": [...]}. Each block has "block_type" (one of: '
        f"{', '.join(sorted(ALLOWED_BLOCK_TYPES))}), \"title\", \"payload\" (object), "
        '"source_refs" (list of the chunk ids you used), "confidence" (0-1 float). '
        'Include 3-6 blocks: at least one explanation ("definition" or "text"), one '
        '"quiz" block whose payload has "question", "options" (list of strings) and '
        '"correct_index" (integer index into options), one "recall_prompt" asking '
        "the learner to explain the topic before moving on, and optionally one "
        '"ordered_relation" block whose payload has "prompt" and "items" (a list of '
        "steps/stages already given in their correct order — the learner will see them "
        "shuffled and has to put them back in this order)."
    )
    user_prompt = (
        f"Course: {context['track'].title if context['track'] else ''}\n"
        f"Module: {context['module'].title if context['module'] else ''}\n"
        f"Lesson topic: {node.title}\n\n"
        f"Source excerpts:\n{excerpts}"
    )

    try:
        raw = generate_json(system_prompt, user_prompt)
    except RuntimeError as exc:
        return {"lesson": lesson, "generation": {"status": "unavailable", "error": str(exc)}}

    blocks = _validate_blocks(raw.get("blocks") if isinstance(raw, dict) else None, node.title)
    if not blocks:
        return {"lesson": lesson, "generation": {"status": "unavailable", "error": "generation_no_valid_blocks"}}

    updated = replace_lesson_blocks(session, int(lesson["id"]), blocks)
    return {"lesson": updated, "generation": {"status": "generated", "chunk_ids": [chunk["id"] for chunk in chunks]}}
