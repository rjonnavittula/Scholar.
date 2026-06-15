# scholar. v4u — new-activity card redesigned (Update 2 of 3)

**No schema change → no DB reset.** Frontend only.

Second of the three agreed updates (animations ✓ → activity card → drag/resize).

## What changed — option A (preset-first + live preview)
The new-activity card now opens with **preset chips** — Class · Lunch · Workout
· Dinner · Custom. Tapping one prefills the title, a sensible time window, the
usual days, and a matching color in a single tap (most activities are routine).

Below the usual title / days / time / color controls, a **live preview chip**
shows exactly how the activity will land on your week — title, the days you
picked, and the time range — in the chosen color, updating as you edit. The
precise time pickers stay, so hitting an exact time is still easy.

Presets only appear when creating; editing an existing activity is unchanged
except it also shows the preview chip. Days, times, color, and the multi-day
save (one row per selected weekday) all work exactly as before.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4u kit
docker compose build --no-cache hive-api && docker compose up -d
```
Hard-refresh.

## Worth a look on first run
- + Add new (activities) → tap **Workout** → title/days/time/color fill in and
  the preview chip shows "Workout · Mon · Wed · Fri · 5:00–6:00 PM" in green.
- Toggle a day or change the time → the preview updates live.
- **block it** → one activity row per selected day, same as before.

## Up next
- Update 3: draggable + resizable activities on the calendar.
