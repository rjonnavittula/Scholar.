# scholar. v4e — subtasks (with time rollup) + notes

Schema change via **Alembic** (migration 0004) — NO `down -v`.

## What's new
- **Subtasks** — open any task (edit) to find a Subtasks section. Type a
  subtask + its own time estimate, press enter. Check them off, delete them.
- **Rollup** — a parent's "time needed" and "remaining" are the **sum of its
  subtasks**, and the **cushion** schedules against that sum (no double-count).
  The parent auto-reads done when all subtasks are done. Verified end-to-end:
  two subtasks (90m + 60m) → parent needs 150m in the cushion.
- **Notes** — a description/notes field on every task.
- Task cards now show "☑ 2/3 subtasks" progress.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4e kit
docker compose build --no-cache hive-api && docker compose up -d
docker compose logs hive-api --tail 6   # alembic applies 0004
```
Normal refresh.

## Tests
`docker compose exec hive-api python -m unittest discover -s tests`
→ 28 passing (cushion/tz/streak/rollup).

## Notes / next
- Subtasks have their own time estimate but no separate due date (they inherit
  the parent's deadline) — matches the "sum" model you picked.
- Still ahead: Pomodoro mode on the timer, repeating tasks, drag tuning,
  calibration engine, onboarding.
