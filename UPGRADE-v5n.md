# scholar. v5n — scheduled Canvas auto-sync (Courses & LMS, part 3 of 3)

**Schema change (adds 3 columns to `settings`), auto-applied on boot. No reset.**
Builds on v5m. Completes the course series.

## What changed
- In **import → Calendar feed**, a new **auto-sync** block: tick *auto-sync in
  the background* and set an interval (hours). scholar then refreshes your
  assignments on its own — no need to open the app and hit sync.
- A background task checks ~1 min after boot, then every 15 min, and runs a
  sync only when your interval has elapsed. It prefers the **ICS feed**; if only
  a **token** is configured it uses that. The last auto-sync time is shown in
  the dialog.
- Hardened so the poller can never crash the app (all failures are swallowed and
  logged), and it's cancelled cleanly on shutdown.

## Apply (migration auto-runs)
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5n.patch
git commit -am "v5n: scheduled canvas auto-sync"
git push
```
No rebuild, no reset. Set it up in import → Calendar feed.

## Heads-up
The background poller does real network I/O, which the offline build can't
exercise — logic is defensive and isolated, but give it one real interval to
confirm in your homelab. Watch it with: `docker compose logs -f hive-api`
(look for any `[autosync]` lines).

## Category status
**Courses & LMS** — Canvas ✓, syllabus PDF ✓, course hub ✓, grades ✓,
scheduled auto-sync ✓. (Brightspace/Moodle intentionally skipped.)
