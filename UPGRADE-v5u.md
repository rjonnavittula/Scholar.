# UPGRADE v5u — Lesson Block Schema

Adds the first DB-backed lesson content spine for Scholar Forge.

## Added
- `LearningLesson` table attached to `LearningNode`.
- `LearningBlock` table with ordered safe block payloads.
- `GET /learn/nodes/{node_id}/lesson` to create/read a starter lesson shell.
- `GET /learn/lessons/{lesson_id}` to read a lesson tree.
- `POST /learn/lessons/{lesson_id}/blocks` to append a safe lesson block.

## Guardrail
Blocks store JSON payloads, not raw generated HTML/JS. Rendering stays controlled by Scholar.
