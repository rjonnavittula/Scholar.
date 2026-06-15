# scholar. v4g — settings fixes + redesigned awake-time

No schema change → **no DB reset.** UI-only.

## Bug fixes
- **Click a task card** (in the list) now opens its editor — no need to find an
  edit button.
- **Appearance actually applies**: font size now scales the whole app (driven
  from the root), density and accent take effect live.
- **Display name** shows as a greeting in the top bar ("good evening, RK").
- **Settings panel**: no more inner scrollbar (panel sizes to fit), the
  COMING SOON badge no longer wraps, field labels/pills no longer collide,
  save button reads as active.

## Redesigned awake-time (the big one)
Replaces the 7 repetitive rows with a visual hybrid:
- **7 day-bars always visible** — each day a 24h track with your awake window
  as an amber band (the ma. way to see your week's rhythm).
- **Default pair** ("usually awake 8:00 → 11:30 PM") with **apply to all**.
- **Weekday / weekend presets** to bulk-set.
- **Tap a day** (its label or time) to reveal inline time pills to edit precisely.
- **Drag the band edges** as a bonus for quick visual tweaks (snaps to 15 min).

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4g kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh.

## Notes
- Light theme still needs a contrast pass — deferred (it's a skin).
- Next: Pomodoro mode, repeating tasks, calibration engine, onboarding.
