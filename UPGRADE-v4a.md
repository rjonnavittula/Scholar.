# scholar. v4a — Alembic, timezone-on-task, Study Streak, view tabs

## What's new
- **Alembic migrations** — this is the LAST manual DB reset. After v4a, schema
  changes are `alembic revision --autogenerate` + `alembic upgrade head`,
  never `docker compose down -v` again.
- **Data capture** — tasks now record `completed_at`; a `TimeLog` table tracks
  focused minutes (powers the streak now, the calibration engine next phase).
  New endpoint `POST /tasks/{id}/log?minutes=N`.
- **Timezone on each task** — the task modal has a location picker: country →
  region (Eastern/Central/… for the US, IST for India, etc.). Auto-detects your
  country, override anytime. Stored per task as `due_tz`; the due time is
  interpreted in that zone.
- **Study Streak bar** — daily efficiency score (throughput + logged effort,
  minus stacking overdue penalty) shown as a flame + intensity dots, with your
  current consecutive-day streak. Engine unit-tested (`tests/test_streak.py`).
- **View tabs** — Day / Week / Month / Next-N. Month grid respects your
  week-start (Settings → "week starts on": Sunday or Monday).

## ⚠ One last DB reset (then never again)
v4a adds columns + the TimeLog table. Because you're coming from v3's schema,
do one final wipe; after this Alembic handles everything.

```bash
cd ~/shared/docker/hive-tasks        # replace contents with the v4a kit first
docker compose down -v               # ⚠ last time
docker compose build --no-cache hive-api
docker compose up -d
docker compose logs hive-api --tail 8   # look for "Uvicorn running"; alembic stamps baseline
curl -s -X POST "http://localhost:8077/auth/keys?label=main"   # fresh key
```
Refresh the browser (cache-bust handles staleness — no hard-reload needed).

## Future schema changes (no reset)
```bash
# edit app/models.py, then:
docker compose exec hive-api alembic revision --autogenerate -m "what changed"
docker compose exec hive-api alembic upgrade head
```

## Tests
```bash
docker compose exec hive-api python -m unittest discover -s tests
# 21 passing: cushion (tz/DST), timezone, streak
```

## Deferred (as agreed)
- **Onboarding wizard** — last, once features settle.
- **v4b (interaction):** drag-to-plan, Plan-on-hover, stopwatch/timer modal,
  collapsible panels.
- **Calibration engine + Ollama insights** — needs the completion/time history
  v4a now starts capturing.
