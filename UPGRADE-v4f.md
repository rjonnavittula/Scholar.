# scholar. v4f — global persistent timer + Plan-button reposition

Schema change via **Alembic** (migration 0005) — NO `down -v`.

## What's new
- **Global timer** — start a timer on any task or subtask and it keeps running
  even after you close the modal. A **pill in the top bar** (⏱ 00:22:34) shows
  it ticking; click the pill to reopen and see exactly what you're timing
  (subtasks show their parent).
- **One at a time** — starting a timer while another runs **warns you** and
  stops the old one first.
- **Survives reload** — the timer is server-backed; refresh the page and the
  pill comes back with the correct elapsed time (computed from start time).
- **Pause / resume / stop & log** — stop banks the minutes to the task (rolls
  up to the parent if it's a subtask). Completing a task auto-stops its timer.
- **Plan button** moved to the **bottom-right** of task cards (was overlapping
  the flag/cushion in the corner).

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4f kit
docker compose build --no-cache hive-api && docker compose up -d
docker compose logs hive-api --tail 6   # alembic applies 0005
```
Normal refresh.

## Watch on first run
- Migration 0005 creates the `activetimer` table — confirm it applies in logs.
- Start a timer, close the modal → pill should keep ticking. Refresh → pill
  should still be there with correct time.

## Next
- Pomodoro mode (layer work/break onto this timer), repeating tasks,
  drag tuning, calibration engine, onboarding.
