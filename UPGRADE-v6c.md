# v6c — Pasted Source Parser

Phase B now has a deterministic parser for pasted text/markdown sources.

## Added

- `LearningSourceSection` table.
- `app/source_parser.py` for local section extraction.
- `POST /learn/sources/{source_id}/parse`.
- `GET /learn/sources/{source_id}/sections`.
- Markdown heading parsing.
- Plain-text numbered heading parsing.
- Idempotent re-parse behavior.

## Still intentionally not included

- PDF upload.
- PDF parsing.
- Qdrant indexing.
- Embeddings.
- RAG lesson generation.
- LLM-generated lesson blocks.

This patch only turns trusted pasted source text into durable sections that later phases can preview, chunk, index, and cite.
