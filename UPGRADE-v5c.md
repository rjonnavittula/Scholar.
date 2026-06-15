# scholar. v5c — Analytics: Future view (Insights pass 2 of 2)

**No schema change → no DB reset.** New endpoint + view; reuses cushion data.
(Versioning moves to phase 5: this is v5c, internal version 0.5.0. Earlier
analytics drops were renamed v5a (Past view) and v5b (top-bar hide).)

## What changed
The Analytics page's **Future** toggle is now live, modeled on Shovel's Future
tab, driven by a new `GET /analytics/future?range=`:

- **Five stat cards** — available study time, tasks due, task workload due,
  time planned, time left to plan (= workload − planned).
- **Task workload due breakdown** — a donut by course (conic-gradient, ma.).
- **Time breakdown** — activity / planned / free study time, stacked.
- **Task workload due each week** — the next 10 weeks, planned + workload
  stacked per week.

Past and Future share the range dropdown; switching the toggle re-fetches the
right endpoint.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v5c kit
docker compose build --no-cache hive-api && docker compose up -d
```
Hard-refresh.

## Worth a look on first run
- ◐ → Analytics → **Future**. The cards should reflect upcoming due tasks and
  your free study time for the range; change the range to compare windows.
- The donut splits workload by course; the weekly chart projects the next 10
  weeks (workload due vs what you've planned).

## Couldn't verify here (no network in build env)
- Live DB aggregation (no sqlmodel offline). The pure date helpers are unit-
  tested (forward_weeks added); the rest mirrors the cushion query patterns.

## Up next
- The **Cushion** + **Timeline** sub-tabs (feasibility curve over the term).
- The AI calibration engine (needs logged history first).
