# scholar. v5z — Phase B source registry foundation

Starts Phase B: trusted source material before generated lessons.

Adds:

- `LearningSource` for registered text/markdown/pdf/url/syllabus material.
- `LearningTrackSource` join table so courses can be grounded by registered sources.
- Source registry API:
  - `GET /learn/sources`
  - `POST /learn/sources`
  - `GET /learn/sources/{source_id}`
  - `DELETE /learn/sources/{source_id}`
  - `GET /learn/tracks/{track_id}/sources`
  - `POST /learn/tracks/{track_id}/sources/{source_id}`
- Localhost auto-key bootstrap for testing, so the browser can mint/store a local key automatically instead of forcing manual key minting every session.

Still not included:

- PDF binary upload.
- Parsing/chunking.
- Qdrant indexing.
- RAG lesson generation.
