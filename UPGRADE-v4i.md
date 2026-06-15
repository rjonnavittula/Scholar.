# scholar. v4i — bug fixes (streak, live timer, sidebar chevrons, drag)

No schema change → **no DB reset.**

## Fixed
1. **Study streak** now shows **7 dots** (Mon–Sun), not 9.
2. **Timer is live** — both the top-bar pill and the modal stopwatch tick every
   second now, not just on pause/interaction. Two root causes fixed:
   - server `started_at` now carries a UTC offset, so the browser computes
     elapsed time correctly (was being read as local time);
   - a single persistent ticker drives all timer displays (the old per-render
     interval was getting cleared).
3. **Sidebar collapse chevrons** (‹ ›) render correctly on first load — they
   were showing raw `\u2039`-style text from an escaping bug in the HTML and JS.
4. **Drag-to-plan offset fixed** — dragged blocks now sit exactly under the
   cursor (was a constant ~10px off because the hour-grid top-inset wasn't
   subtracted). Block heights are also correct now (a 90-min block is the right
   height). Cancelling a drag no longer leaves a ghost block behind.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4i kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh.

## Still on the list (next rounds)
- Settings → full-screen Apple-style window (you picked this).
- Calendar should span full width; Month view uses the space; **Day view**
  is broken/empty — needs building.
- Dark/light toggle symbol above the gear in the sidebar.
- Sidebar section titles + "add"/"configure" too small on large monitors.
