# scholar. v4p — task detail rebuilt as the "runway command center"

**No schema change → no DB reset.** Frontend-only (plus reuse of existing
endpoints). The sidebar-click task view is no longer a form — it's a workspace
organized around the deadline.

## What changed (sidebar-click / edit view)
Opening a task now shows:

- **Title** (inline-editable) + **flag** and **mark-complete** icons up top.
- **Chips** — course · category · due. Click any chip (or "edit details") to
  reveal the full editor (course/category/due/timezone/time-needed) — same
  controls as before, just folded away until you want them.
- **Runway card** — the centerpiece. A track from now → due with:
  - your **cushion** as the headline, colored green/yellow/red and showing the
    real number (`Xh Ym cushion` or `Xh Ym short`) straight from the engine;
  - a **slack region** (now → due) tinted by that same level;
  - **ticks** for every planned study block on this task;
  - a **now** marker and a `Nd to due` axis label;
  - a **TIME USED / STILL NEED** fill underneath.
- **Work zone** — a compact stopwatch (segmented, follows whichever
  task/subtask is timing) beside the **subtask breakdown** (this task · directly
  + each subtask, each with its own play; the single global timer still rules).
- **Notes** — folded behind a toggle.
- **Footer** — move to trash · cancel · save (mark-complete lives up top).

New tasks still open the simple create form (no runway until it exists).

The runway reads real data: `cushion_min` + `level` from `/cushion`, planned
blocks from `/planned`, and start/due/created from the task. No new endpoints.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4p kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh.

## Worth a look on first run
- Open a task with a due date from the sidebar → the runway shows; the cushion
  headline should match the top-bar cushion chip's health for that task.
- Plan a couple of study blocks for it → ticks appear on the track.
- Log time (start the work-zone stopwatch, or a subtask's) → the TIME USED /
  STILL NEED fill moves; reopen to see it updated.
- Click a chip or "edit details" → the editor unfolds; save persists as before.
- Narrow the window (<560px) → the work zone stacks.

## Next (unchanged backlog)
Pomodoro mode on the timer, repeating tasks, drag tuning, calibration, onboarding.
