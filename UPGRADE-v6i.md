# v19 — Parser Hardening

This patch starts Phase C by making source parsing safer and more stable before chunking.

## Added

- Parser version metadata on parsed source sections.
- Heading path metadata for nested headings.
- Markdown Setext heading support.
- Roman numeral heading support.
- All-caps/plain-text heading improvements.
- Better PDF page marker detection.
- PDF form-feed page break support.
- Front matter cleanup.
- Hyphenated line-break cleanup.
- Protection against bullets/tables being misread as headings.
- Code fence protection so code comments are not parsed as headings.
- Tests for parser edge cases.

## Not included yet

- Durable chunk table.
- Chunking engine.
- Embeddings.
- Qdrant indexing.
- RAG lesson generation.
