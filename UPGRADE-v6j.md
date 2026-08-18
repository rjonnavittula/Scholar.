# v20 — Chunk Model

Phase C now has a durable chunk schema.

## Added

- `LearningSourceChunk` SQLModel table.
- Alembic migration `0014_learning_source_chunks`.
- `app/chunk_store.py` helpers for storing and listing chunks.
- Stable chunk hashes.
- Cheap deterministic token estimates.
- Source deletion now removes chunks.

## Not included yet

- Automatic chunking engine.
- Chunk API routes.
- Chunk preview UI.
- Embeddings.
- Qdrant indexing.
- RAG lesson generation.
