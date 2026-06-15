# scholar. v4n — stopwatch breakdown + per-subtask time tracking

**No schema change → no DB reset.** The parent's direct time was always stored
in `time_spent_min`; we'd just been discarding it on rollup. Now it counts.

## What changed

### Time model (the substance)
A parent task's total time is now **sum of its subtasks + any time logged
directly on the parent**. Before, logging time on a parent that had subtasks
was silently thrown away by the rollup. Now:
- `app/rollup.py` — engine sees `spent = sum(subtasks) + parent.direct`
  (cushion + streak stay consistent; `remaining = needed - that`).
- `app/api.py` `list_tasks` — same for the API: parent `time_spent_min` =
  subtasks' spent + parent direct, and it now exposes **`direct_spent_min`** on
  every task so the UI can show a "this task · directly" line.
- New rollup test (`test_parent_direct_time_adds_to_children`): 30 + 30 + 20
  direct → 80 spent, 40 remaining. Suite is **29 passing**.

### Calendar-click stopwatch (the summarized popup)
- **No subtasks:** an "I'll work on…" field. Press start with text in it and you
  get an inline choice — **time the whole task**, or **spin the text into a new
  subtask and time that**. (Empty field → just times the task.)
- **Has subtasks:** a **breakdown** under the clock — `total NhNm / planned`,
  a "this task · directly" row, and one row per subtask, each with its own
  play. Tap any row to switch the running clock to it; the active row is lit and
  its button flips to pause. One global timer still — switching warns/stops the
  old one as before.

### Sidebar edit view
- The subtasks section gained a **TIME USED / STILL NEED** bar, a
  "this task · directly" play row, and per-subtask **logged / needed** with a
  play button on each. Same single global timer; the active row is highlighted.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4n kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh.

## Worth a look on first run
- Open a task with subtasks **from the calendar** → breakdown shows; tap a
  subtask's ▶, close the modal, the pill keeps ticking that subtask.
- Stop it, reopen the parent → that subtask's logged time went up, and the
  parent **total** = subtasks + anything you'd logged on the parent directly.
- Open a task with **no** subtasks from the calendar, type in "I'll work on…",
  press start → the parent/subtask choice appears.

## Next (unchanged backlog)
Pomodoro mode on the timer, repeating tasks, drag tuning, calibration, onboarding.
