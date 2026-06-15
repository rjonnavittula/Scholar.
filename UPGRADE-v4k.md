# scholar. v4k — FullCalendar (real drag/resize, Day & Month views) + settings grid

No schema change → **no DB reset.** Big front-end change.

## Why
Hand-rolled drag kept breaking. This swaps the **center calendar grid** for
**FullCalendar v6** (open-source, MIT) — keeping your sidebar, task panel,
top bar, cushion/streak/timer, and the ma. theme. FullCalendar handles
week / day / month rendering + **drag-move + edge-resize** natively.

This fixes in one move: the drag offset, the resize mess, the empty **Day
view**, and the cramped **Month view** (now full grid).

- Loads FullCalendar from CDN (one `<script>`, self-contained, injects own CSS).
- Themed into ma. via `--fc-*` variable overrides (amber-on-dark).
- Drag a block to move; grab top/bottom edge to resize; drag a task card onto
  the grid to plan it; click a block for its menu/timer. All wired to the same
  backend endpoints as before.

## Settings
- Panes are now a **responsive CSS grid** (`auto-fit` / `minmax`) — fields flow
  into 1–2 columns by width instead of one cramped stack. Awake-time and
  Notifications stay single-column for readability.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4k kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh. **First load fetches FullCalendar from the CDN — you need
internet the first time** (it'll cache after).

## Watch on first run (I can't render FC in the build sandbox)
- The calendar should appear in week view, full width, ticking now-indicator.
- Day / Month tabs should switch views.
- Drag a block (moves), grab its top/bottom edge (resizes), drag a task card in
  (plans it). Each should persist after refresh.
- If the calendar area shows "calendar library failed to load", the CDN was
  blocked — tell me and I'll bundle FullCalendar locally instead.

## Still queued
- Dark/light toggle symbol above the gear; larger sidebar section titles.
