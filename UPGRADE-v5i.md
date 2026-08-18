# scholar. v5i — Pomodoro + break reminders (closes Time tracking)

**No schema change → no DB reset.** Frontend only (logs via the existing
`/tasks/{id}/log` endpoint).

## What changed
- The 🍅 button in the top bar now opens a **Pomodoro** panel.
- Pick a task, hit **start**: a focus countdown runs (default 25 min), then a
  short break (5), cycling to a long break (15) every 4th focus session. Cycle
  dots show where you are in the set.
- **Real logging:** every completed focus phase logs its minutes to the task
  (so cushion, time-spent and the CSV export all reflect Pomodoro work).
  Skipping or stopping mid-focus logs the elapsed minutes only.
- **Gentle reminders** at every transition: an in-app toast, a browser
  notification (it asks permission on first start), and a soft beep.
- **pause / resume / skip / stop** controls, and a **settings** drawer for the
  focus / break / long-break lengths, cycles-per-long-break, and an
  auto-start-next-phase toggle (saved in your browser).
- It runs on its own ticker independent of the dialog (close it and focus keeps
  counting; the 🍅 stays lit), and **resumes across a page reload**.

## Apply
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5i.patch
git commit -am "v5i: pomodoro + break reminders"
git push
```
Refresh the browser; click 🍅.

## Category status
**Time tracking — closed.** ✓ timer · ✓ manual logging · ✓ CSV export ·
✓ Pomodoro · ✓ break reminders.

(Note: Super Productivity's CBT "anti-procrastination" prompts are a separate,
optional flavor we can add later if you want them — the core break-reminder
behavior is covered.)
