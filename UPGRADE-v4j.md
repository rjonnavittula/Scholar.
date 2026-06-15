# scholar. v4j — settings morph + resize rebuild + passed-time shading

No schema change → **no DB reset.**

## Settings
- Now a **properly-sized wide card** (no more tall narrow column) that
  **morphs open** — scales up from center with a fade. Content fits, the
  save/cancel bar stays pinned at the bottom.

## Calendar drag / resize (bugs)
- **Resize rebuilt**: each block has **top and bottom** resize edges with small
  grab-tabs that appear on hover. Dragging an edge resizes *only* that edge.
- **Fixed the "resize then moves" bug** — resize and move are now fully
  separate; resizing no longer triggers the move behavior afterward.

## Display
- A **subtask now shows its parent** ("↳ part of <task>") in the edit modal
  (the timer modal already did).
- **Passed time is shaded darker** — past days and today's elapsed hours get a
  tint, and any planned block sitting in passed time is dimmed (still visible,
  just clearly "behind you").

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4j kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh.

## Still queued
- Calendar full-width; Month view uses the space; **Day view** still needs
  building (currently empty).
- Dark/light toggle symbol above the gear; larger sidebar section titles.
