# scholar. v4t — canvas card animations (Update 1 of 3)

**No schema change → no DB reset.** CSS only.

First of the three agreed updates (animations → activity card → drag/resize).

## What changed
The canvas card now animates like the settings card:
- the modal still rises in with the shared `pop` entrance, and
- each method tab panel (Access token / Calendar feed / Quick script) does the
  settings `spaneIn` rise-and-fade (.24s) when you switch tabs — the same
  motion the settings panes use.
- the active tab pill now glides between tabs instead of snapping.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4t kit
docker compose build --no-cache hive-api && docker compose up -d
```
Hard-refresh.

## Up next
- Update 2: new-activity card → **option A** (preset-first + live preview).
- Update 3: draggable + resizable activities on the calendar.
