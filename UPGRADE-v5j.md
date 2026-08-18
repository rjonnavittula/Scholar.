# scholar. v5j — Cushion + Timeline insights (closes Insights)

**No schema change → no DB reset.** Frontend only; both tabs read the existing
`/cushion` engine output.

The Streak tab + both heatmaps were already built — this fills the last two
stubs, so the whole Insights category is now live.

## What changed — two new Insights sub-tabs
- **Cushion** — a feasibility snapshot:
  - a headline card: on-track (green) or behind (red), with your total cushion;
  - **cushion by task**, tightest-first, each with a green/yellow/red bar and
    its value (e.g. `+2h 30m` / `−1h 00m`);
  - **free study time ahead** — a 14-day bar chart of free minutes per day,
    dotted where tasks are due.
- **Timeline** — *cushion over time*: a line chart of cumulative work due vs
  free time available across your due dates (the exact numbers the engine
  already computes per task). It calls out the first "crunch" date where demand
  outruns your free time, or confirms you're feasible throughout. Hover any
  point for that task's cumulative need / free / cushion.

## Apply
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5j.patch
git commit -am "v5j: cushion + timeline insights"
git push
```
Refresh; ◐ Insights → Cushion / Timeline.

## Category status
**Insights — closed.** ✓ Past · ✓ Future · ✓ Streak · ✓ heatmaps (grid + month)
· ✓ Cushion · ✓ Timeline.

Three categories down (Planning & Calendar, Time tracking, Insights). Biggest
remaining: **Task management** (real priority levels, repeating tasks, the
filter panel, boards) and **Courses & LMS**.
