# v23 — Phase C Hardening

This patch closes Phase C by tightening chunk behavior before vector indexing.

## Added

- Word-boundary-safe chunk overlap.
- Duplicate chunk prevention when chunking without replacement.
- Phase C audit fields for chunked sources and token totals.
- Tests for overlap quality, duplicate prevention, and audit counts.

## Still not included

- Qdrant indexing.
- Embeddings.
- Semantic search.
- RAG lesson generation.
