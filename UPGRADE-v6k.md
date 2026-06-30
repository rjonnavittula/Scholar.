# v21 — Chunker Engine

Phase C now has deterministic chunking for parsed sources.

## Added

- `app/chunker.py`.
- Deterministic section-to-chunk conversion.
- Character-window splitting with bounded overlap.
- Stable chunk metadata with `source-chunker-v1`.
- Automatic parse-before-chunk behavior when a source has no sections yet.
- Replace-safe chunk regeneration.

## Not included yet

- Chunk API routes.
- Chunk UI preview.
- Embeddings.
- Qdrant indexing.
- RAG lesson generation.
