# UPGRADE v5s — Forge backend source parser

Adds the first backend contract for Scholar Forge ingestion.

- New deterministic parser in `app/learn_parser.py`
- New authenticated `POST /learn/parse-source` endpoint
- Parser classifies source text, extracts track title, role, modules, rule buckets, and stable source hash
- Adds parser unit tests

This is intentionally deterministic. No Ollama, DB persistence, RAG, or lesson generation is added in this step.
