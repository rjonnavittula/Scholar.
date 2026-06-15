# scholar. v4v — Analytics page, Past view (Insights pass 1 of 2)

**No schema change → no DB reset.** New endpoint + new view; uses data you
already capture (TimeLog is timestamped, PlannedBlock, Activity, availability).

## What changed
The ◐ rail button now opens a real **Analytics** page (was a "phase 5" toast),
modeled on Shovel's Analytics tab in the ma. aesthetic:

- **Sub-tabs** Analytics · Cushion · Timeline (the latter two are stubbed for a
  later pass), a **Past / Future** toggle, and the full **range dropdown**
  (Today … Last month … All time).
- **Past view** charts, all driven by a new `GET /analytics/past?range=`:
  - **How I spent my time** — a stacked bar of study time (used / planned-but-
    not-used / free) plus activity-event hours in range.
  - **Time I spent on tasks** — total, the most time-consuming task, and a
    per-task bar list (colored by course).
  - **Am I following my plan?** — planned vs. used per day.
  - **Time I spent on tasks each week** — the last 6 weeks.
- **Future** toggle shows a "coming next" note (that's pass 2).

### Honest mapping note
Shovel splits calendar time into *Course / Activity / Custom events*. scholar
only models Activities and study blocks, so the breakdown is folded into a
single "activity events" figure rather than faking the three-way split.

New code: `app/analytics_util.py` (pure range/week helpers, 8 unit tests) and
`app/analytics.py` (aggregation), plus the `/analytics` router and the front-end
view. Suite is **45 passing**.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4v kit
docker compose build --no-cache hive-api && docker compose up -d
```
Hard-refresh.

## Worth a look on first run
- Click the ◐ rail icon → Analytics opens; the calendar toolbar/panel hide.
- Change the range dropdown → charts refetch.
- If you've logged time on tasks, "Time I spent on tasks" and the weekly bars
  populate; otherwise they read empty (expected — they need logged history).
- ⌂ goes back to the calendar.

## Couldn't verify here (no network in build env)
- The live aggregation against a real DB (no sqlmodel offline). The pure date
  helpers are unit-tested; the aggregation mirrors the tested cushion/streak
  query patterns. Eyeball the numbers against your own logged time.

## Up next
- Pass 2: the **Future** analytics view (available study time, tasks due,
  workload-due breakdown pie, time breakdown, workload-per-week).
- Then the **Cushion** + **Timeline** sub-tabs (feasibility curve).
