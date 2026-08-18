# Upgrade v5p — HIVE-Courses v1.1 Learning Map

This patch upgrades the first HIVE-Courses shell into a more game-like learning map.

## Adds

- Course hero card with task-mastery ring
- Game HUD: paths, due-soon pressure, workload, Scholar XP, streak
- Boot.dev-style mission node map for each course
- Brilliant-style next-mission panel
- Source-signal cards for Canvas, syllabus, lecture rhythm, and future slide uploads
- Urgency states: clear, open, due soon, late, locked

## Data source

This is still frontend-only. It derives its state from existing Scholar data:

- `courses`
- `tasks`
- `activities`
- `planned`
- `streak`
- Canvas status/task source fields
- syllabus-derived task categories

## Next

v2 should add the first backend learning API and local Ollama lesson generation.
