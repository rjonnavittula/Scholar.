# v25 — Ollama Embedding Client

Phase D now has an Ollama embedding client for Scholar memory.

## Added

- Runtime embedding config.
- Ollama `/api/tags` health check.
- Single-text embedding helper using `nomic-embed-text`.
- Embedding preview endpoint that returns dimension/checksum, not the full vector.
- Embedding layer surfaced in the memory tabs.

## Still not included

- Qdrant upserts.
- Semantic search.
- RAG context building.
- OKF export/import.
