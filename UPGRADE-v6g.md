# v18 — Course UI Composition Pass

This patch improves Scholar Courses before Phase C begins.

## Added

- Wider responsive course cards to reduce dead space on large screens.
- Course map layout with a main module stage and right study panel.
- Compact course rail with course stats instead of cramped source cards.
- Study Focus card showing the next module and mastery progress.
- Linked sources moved into the right study panel.
- Stronger lesson workspace hero so the lesson title and state remain visible.
- Empty lesson shell with recall workspace while grounded blocks are not generated yet.
- Local browser persistence for recall text.
- Simple selected state for quiz options.

## Design intent

Use progressive disclosure: keep the course rail minimal, move detailed source management into the study panel, and give empty lesson states a clear next action instead of blank space.

## Not included

- Phase C parsing/chunking beyond current source sections.
- Qdrant indexing.
- RAG lesson generation.
