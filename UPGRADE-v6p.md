# v25a — Scholar Interaction Design System

This patch adds the first Brilliant-inspired interaction grammar for Scholar while keeping the Industrial Ma visual direction.

## Added

- Motion utility classes for staged entry, card lift, pop-in modals, loading scan, and resolved button states.
- Tactile-feeling button and card interactions using tiny sequential state changes.
- Lightweight browser vibration helper when supported by the device.
- Dashboard course cards now use progressive step dots instead of only passive metadata.
- Soulful empty-state mascot built in CSS only, with no remote assets.
- Create Course modal now has a three-step flow marker and a completion state.
- Course open and memory layer changes now trigger subtle interaction feedback.

## Duplicate Course Guard

- Creating the same pasted course again reopens the existing course instead of creating a duplicate.
- Duplicate detection uses `source_hash` first.
- When no hash is available, it falls back to normalized title plus module sequence.
- Course list rendering also deduplicates display results as a defensive UI layer.

## Not included yet

- Full lesson-game engine.
- Full mascot illustration set.
- Qdrant chunk upsert.
- Semantic search.
- RAG answers.
