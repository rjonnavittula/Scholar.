# v5y — Phase A Course Hardening

Phase A now has the final usability and safety pass for DB-backed Scholar Courses.

## Added
- Course progress summaries in list/detail payloads:
  - mastery
  - module_count
  - completed_module_count
  - next_module_title
- `DELETE /learn/tracks/{track_id}` for cleaning up test/generated course maps.
- Manual cascade cleanup for course tracks, modules, nodes, lesson drafts, and blocks.
- Course card progress bars and next-module hints.
- Visual stabilization for the Phase A course workspace: right task panel auto-close, cleaner cards, fixed map pathing, subject badges, centered lesson actions, and no distracting scanner panel.
- Course Map delete action.
- Locked module hinting and disabled locked node buttons.
- Test cleanup disposes SQLite engines to reduce ResourceWarning noise.

## Still intentionally not included
- RAG-backed lesson generation.
- PDF/source registry.
- mastery review scheduling.
- full visual redesign.

This closes Phase A: create, store, display, open, progress, unlock, and delete course skeletons.
