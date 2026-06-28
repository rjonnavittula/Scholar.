# v6d — File Upload Source Intake

Phase B now accepts uploaded source files.

## Added

- `POST /learn/sources/upload`
- `app/source_upload.py`
- Text/Markdown/PDF intake path
- Upload size guard
- File metadata on registered sources
- Optional `parse_now=true` upload parsing
- UI file picker inside Add Source
- `Api.upload()` for `FormData`

## Notes

- This is still source intake only.
- PDF support extracts text with `pypdf`; OCR is not included.
- RAG, embeddings, and generated lessons are still later phases.
