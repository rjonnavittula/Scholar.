# scholar. v4o — calendar-click stopwatch rebuilt to the Shovel layout (ma.)

**No schema change → no DB reset.** Adds one timer endpoint (`/timer/cancel`),
no new tables.

## What changed
The calendar-click popup was rebuilt to match Shovel's stopwatch screen, in ma.:

- **Header** — course · category crumb (amber) + a close (×).
- **Title row** — task title with an "open full view" (↗, opens the edit modal)
  and a **flag** toggle that lights amber when on.
- **Meta row** — `Start` pill (the planned block's start, or the task start
  date) and `Time planned` pill (`1h 00m`).
- **"I will work on…"** box — the big intent field. With no subtasks, pressing
  play with text in it still pops the **time-the-task / make-a-subtask** choice.
- **Stopwatch bar** — a single rounded control: play/pause · the **segmented
  readout** (kept, Cormorant) · **reset** (↻, discards the running session and
  logs nothing) · **check** (✓ = stop & log). To the right, when opened from a
  planned block: **duplicate block** (⧉) and **remove from calendar** (×).
- **Manual log** — the quiet "or log [min] add" row stays; "mark block studied"
  joins it when relevant.
- **Breakdown** (only when the task has subtasks) — total + a "this task ·
  directly" row + one row per subtask, each with its own play; tap to switch the
  single global timer. Active row lit amber.
- **Footer** — "Done with the entire task?  [Mark Task Complete]".

The reset control is new: `POST /timer/cancel` clears the active timer without
banking any minutes (vs. stop, which logs).

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4o kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh.

## Worth a look on first run
- Click a due/planned item on the calendar → the new layout opens.
- Start, then **reset (↻)** → clock returns to 00:00:00 and nothing is logged.
- **check (✓)** → stops & logs the session, closes.
- Open a task with subtasks → the breakdown shows under the bar; tap a subtask's
  play to time it.
- Resize narrow (<520px) → Start/Time-planned stack, readout shrinks.

## Next (unchanged backlog)
Pomodoro mode on the timer, repeating tasks, drag tuning, calibration, onboarding.
