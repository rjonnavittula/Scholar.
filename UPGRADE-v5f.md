# scholar. v5f — task sidebar: scroll, collapsible groups, sort, cushion button

**No schema change → no DB reset.** Frontend only.

First half of the task-list redesign (filters are v5g next).

## What changed
- **The task list scrolls on its own.** The search box + tools stay pinned at
  the top; only the grouped task list scrolls beneath them (hover-only bar).
- **Categories collapse.** Each due-group header (Overdue, Due: Today, … No due
  date) is now a toggle with a ▾/▸ chevron and a right-aligned count — click to
  fold a group away.
- **Sort tasks.** A ⇅ button opens a sort popover: *Soonest / Latest first*,
  and sort by *Due date · Total estimate · Time still needed · Time left to plan
  · Priority*. Sorting orders tasks within each group.
- **Calculate cushion.** A ◷ button recomputes the cushion on demand
  (re-queries the engine), refreshes the per-task cushion shown on each card and
  the top cushion chip, and spins while it works.

## Apply
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5f.patch
git commit -am "v5f: task sidebar scroll/collapse/sort/cushion"
git push
```
Backend reloads itself; refresh the browser for the UI.

## Next — v5g (filters)
The filter panel (To Do/Completed, due ranges, by course/activity, etc.). One
mapping note to settle then: Shovel has High/Med/Low/None priority, but scholar
only stores a priority *flag* — so "priority" filtering will be flag-based
unless we extend the model.
