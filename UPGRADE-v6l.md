# v21 — Chunk API + UI Preview

This patch exposes deterministic source chunks through the Scholar API and adds a preview workflow in the source modal.

## Added

- `POST /learn/sources/{source_id}/chunk`
- `GET /learn/sources/{source_id}/chunks`
- Source response `chunk_count` metadata
- Source audit `total_chunks` count
- Source preview chunk column
- Chunk / Re-chunk Source action in the UI

## Still not included

- Qdrant indexing
- Embeddings
- Semantic search
- RAG lesson generation
