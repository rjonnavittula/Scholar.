# scholar. v3 — timezones + DST + calendar alignment

## What changed
- **Real multi-timezone support.** Everything stores in UTC; wall-clock times
  are interpreted in named IANA zones, so DST (EST↔EDT, PST↔PDT) is handled
  automatically — no fixed offsets.
  - `home_tz` — your current physical zone. Awake hours + study blocks follow it.
  - `school_tz` — where due dates are anchored (a "11:59pm ET" deadline stays
    11:59pm ET no matter where you are).
  - Each **activity** carries its own `tz` (a physical ET lecture stays ET even
    while you're in PT; default = home_tz).
- **Calendar alignment fixed** — the corner-cell class conflict that pushed
  columns out of line is gone; hour labels and day columns now share one
  baseline.
- New endpoints: `GET /config/timezones` (picker list); `home_tz`/`school_tz`
  in `GET/PUT /config/settings`.
- Engine is fully tested: `python3 -m unittest tests.test_cushion tests.test_timezone`
  → 14 passing (incl. spring-forward, fall-back, PT/ET split, ET-anchored due).

## ⚠ Schema change — fresh DB required
Activity gained `tz`; Settings gained `home_tz`/`school_tz`. SQLModel's
`create_all` won't alter existing tables, so wipe + recreate:

```bash
cd ~/shared/docker/hive-tasks      # (replace the folder contents with the v3 kit first)
docker compose down -v             # ⚠ deletes the DB volume
docker compose build --no-cache hive-api
docker compose up -d
docker compose logs hive-api --tail 5     # wait for "Uvicorn running"
curl -s -X POST "http://localhost:8077/auth/keys?label=main"   # fresh key
```
Hard-refresh the browser (Ctrl+Shift+R) and paste the new key.

Then set your zones (PT student / ET school):
```bash
KEY=hive_...
curl -s -X PUT http://localhost:8077/config/settings -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"home_tz":"America/Los_Angeles","school_tz":"America/New_York"}'
```

## Known limitation (next turn)
The **frontend** renders in single-zone mode for now — the backend math is
fully zone-correct, but the UI doesn't yet show per-activity tz labels or the
auto-detect/override zone switcher. That UI layer is the next phase. Nothing
regresses: the calendar works, the cushion is correct, due dates are honored
in school_tz under the hood.
