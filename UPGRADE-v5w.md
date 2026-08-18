# UPGRADE v5w — Course UX Cleanup

This patch removes the temporary Forge wording from the user-facing course flow.

## Changes

- Renames visible Forge labels to course labels:
  - Forge Topology -> Scholar Courses / Course Map
  - Neural Archives -> Course Library
  - Text Node -> Create Course
  - DB Lesson Shell -> Lesson Draft
- Improves deterministic title extraction so pasted system prompts no longer create cards named `System Prompt`.
- Adds module previews to course cards using `module_titles` from `GET /learn/tracks`.
- Updates lesson shell copy to sound like a real course draft, not a database debug screen.
- Uses the Python course prompt as the default programming test shape.

## Still not included

- No RAG.
- No lesson generation.
- No progress mutation.
- No full visual redesign pass.
