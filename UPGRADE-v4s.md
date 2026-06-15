# scholar. v4s — Canvas without an API token (calendar feed + quick script)

**Adds migration 0006** (one new column `settings.canvas_ics_url`). It applies
automatically on boot (`alembic upgrade head`) — no reset, no data loss.

## Why
Some schools disable personal access-token creation, and raw session cookies are
a dead end (httpOnly, expire hourly, SSO). So the canvas card now offers two
cookieless paths alongside the token.

## What changed
The canvas card has three method tabs:

1. **Access token** — unchanged (the full-power path).
2. **Calendar feed (ICS)** — paste your Canvas calendar feed URL
   (Canvas → Calendar → Calendar Feed). scholar stores it and polls it
   server-side via `POST /integrations/canvas/sync-ics` — no token, no cookie,
   pure outbound HTTPS, so it works even while scholar is on plain http. Turns
   assignment due dates into tasks.
3. **Quick script** — a clipboard bookmarklet. Run it while logged into Canvas
   (bookmark or console); it fetches your courses + upcoming assignments via your
   existing session (same-origin) and copies them to your clipboard. Paste back
   into scholar → `POST /integrations/canvas/import`. The paste step is
   same-origin to scholar, so no CORS and no mixed-content issue on http. When
   you add HTTPS via NPM later, nothing here needs to change.

**Dedup:** all three paths upsert by `external_id = canvas:{assignment_id}` — the
ICS parser pulls the id out of each event's UID — so token sync, the feed, and
the script merge into the same tasks instead of duplicating.

New code: `app/ics.py` (dependency-free VEVENT parser, 8 unit tests), importer
helpers in `app/integrations.py`, and two endpoints. Suite is **37 passing**.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4s kit
docker compose build --no-cache hive-api && docker compose up -d
```
Migration 0006 runs on start. Hard-refresh the web UI.

## Worth a look on first run
- Canvas card → Calendar feed → paste your feed URL → "save & sync now" →
  due-dated assignments appear as tasks.
- Canvas card → Quick script → copy the script, run on Canvas, paste back,
  import → courses + assignments appear.
- Run the token sync (if configured) and a feed sync — the same assignment
  should update in place, not double.

## Couldn't verify here (no network in build env)
- The live ICS fetch + the exact "Calendar Feed" wording/path in PSU's Canvas —
  confirm against your account. The parser itself is tested against a realistic
  Canvas feed sample (TZID→UTC, folded lines, assignment-id extraction).

## Next (unchanged backlog)
Scheduled auto-poll of the feed, Pomodoro mode, repeating tasks, calibration.
