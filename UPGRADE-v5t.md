# UPGRADE v5t — DB-backed Forge tracks

Adds the first persistence layer for Scholar Forge.

## Added
- `LearningTrack`, `LearningModule`, and `LearningNode` SQLModel tables.
- Alembic migration `0010_learning_tracks`.
- `app/learn_store.py` persistence helpers.
- `/learn/tracks` list/create endpoints.
- `/learn/tracks/from-source` parse-and-save endpoint.
- `/learn/tracks/{track_id}` nested tree endpoint.
- Unit tests for track/module/node persistence.

## Still intentionally not included
- No lesson generation.
- No RAG.
- No source registry.
- No frontend wiring yet.
