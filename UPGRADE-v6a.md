# HIVE Scholar v6a — Source Registry Dedupe

Patch 014 tightens the Phase B source registry.

## Adds

- Exact source deduplication by `content_hash`, `source_type`, and `body_text`.
- Duplicate source creation now returns the existing source instead of creating a new row.
- Duplicate responses include `deduplicated: true`.
- Track-source linking remains idempotent and now returns the effective `role`.
- Tests for source dedupe and link role updates.

## Still Not Included

- PDF upload UI.
- Document parsing/chunking.
- Qdrant indexing.
- RAG lesson generation.
