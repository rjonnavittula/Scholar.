# v24 — Phase D Qdrant Memory Foundation

This patch starts Phase D without indexing chunks yet.

## Added

- Qdrant runtime configuration helper.
- Qdrant health check helper.
- Scholar chunk collection ensure helper.
- `GET /learn/memory/layers`.
- `GET /learn/memory/qdrant/health`.
- `POST /learn/memory/qdrant/ensure`.
- Course UI memory-layer tabs: SQL, Qdrant, RAG, OKF.
- OKF stays visible as a planned portable memory layer.

## Not included yet

- Ollama embeddings.
- Chunk vector upserts.
- Semantic search.
- RAG context builder.
- OKF export/import implementation.
