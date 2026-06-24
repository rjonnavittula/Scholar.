# scholar. v5h — CSV time-log export (Time-tracking close-out, 1 of 2)

**No schema change → no DB reset.** New endpoint + Insights button.

First of two to close the Time-tracking category (Pomodoro + breaks land in v5i).

## What changed
- **Export your time logs as a CSV timesheet.** An **export** button now sits in
  the Insights controls (next to the range dropdown). It downloads every
  TimeLog in the selected range — columns: date, time, task, course, category,
  minutes, source — as `scholar-timelog-<range>.csv`.
- Backed by `GET /analytics/export?range=…` (returns `{ filename, csv, count }`),
  so H.I.V.E. components can pull the same timesheet programmatically.

## Apply
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5h.patch
git commit -am "v5h: CSV time-log export"
git push
```
Refresh the browser; ◐ Insights → pick a range → export.

## Category status
**Time tracking** — timer ✓, manual logging ✓, CSV export ✓ (new). Remaining to
close: **Pomodoro + break reminders** (v5i, builds on the existing timer).
