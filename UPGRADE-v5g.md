# scholar. v5g — 2-day view (closes the Planning & Calendar category)

**No schema change → no DB reset.** Frontend only.

With this, the whole Planning & Calendar column in the feature matrix is ✓ vs
both Shovel and Super Productivity (scholar was already ahead on the
cushion/feasibility piece).

## What changed
- New **2 Day** button in the calendar view tabs (Day · 2 Day · Week · Month).
- It shows today + tomorrow (a fixed 2-day timeGrid), and the ‹ › nav pages by
  two days at a time. All drag-to-plan / resize / activity rendering work exactly
  as in the week view.

## Apply
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5g.patch
git commit -am "v5g: 2-day calendar view"
git push
```
Refresh the browser.

## Category status
**Planning & Calendar — closed.** ✓ drag-to-plan · ✓ week/month · ✓ 2-day ·
✓ recurring activities · ✓ overload/feasibility (cushion engine).

Next easiest to close: **Time tracking** (timer + logging already ✓; gaps are
Pomodoro, CSV/JSON export, break reminders) — or your pick.
