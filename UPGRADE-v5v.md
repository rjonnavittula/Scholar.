# UPGRADE v5v — DB-backed Forge UI wiring

## What changed
- Wired the Scholar Forge frontend to backend learning routes.
- Replaced localStorage as the primary source of truth for Forge tracks.
- Text ingestion now calls `POST /learn/tracks/from-source`.
- Dashboard reads `GET /learn/tracks`.
- Course topology reads `GET /learn/tracks/{track_id}`.
- Lesson screen reads `GET /learn/nodes/{node_id}/lesson`.

## Still not included
- Completion/mastery mutation endpoints.
- Source Registry/RAG.
- Generated lesson content.
- UI redesign pass.
