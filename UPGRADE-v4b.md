# scholar. v4b — the interaction layer

No schema change → **no DB reset.** Apply on top of v4a.

## What's new
- **Plan a task three ways:**
  1. **Drag** a task card from the right panel onto a calendar slot (ghost
     preview shows where it lands).
  2. **Plan button** (appears on hover over a task card) → places a default
     block you can then drag/resize.
  3. **Plan exactly…** dialog → type day / start / minutes for precise placement.
- **Blocks:** default to the task's remaining time (capped at a first 2h chunk);
  drag to move, drag the bottom edge to resize, and create **multiple blocks
  per task** (a 6h task → several blocks across days). Task cards show
  "Xh of Yh planned."
- **Stopwatch / timer modal** (click any planned block, or a task): start/pause
  a timer that **logs minutes** to the task (feeds the streak + future
  calibration), or log minutes manually. **"Mark task complete" is a separate
  explicit button** — the timer never auto-completes.
- **Collapsible panels:** tabs on the left and right edges hide the sidebar /
  task panel for a focused calendar.

## Apply
```bash
cd ~/shared/docker/hive-tasks      # replace contents with the v4b kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh (cache-bust handles it). No `down -v`.

## Heads-up (drag feel)
Drag/resize interactions are the kind of thing that often want one round of
tuning (snap increments, grab feel). If the drag feels off, tell me what and
I'll adjust the snap/threshold — the logic is in calendar.js `startDrag`.

## Still ahead
- Onboarding wizard (the finale).
- Calibration engine + Ollama insights (now that v4a/b capture completion &
  time-log history to learn from).
