# scholar. v4c — light mode, animated collapse, animations, settings panel

Schema change is handled by **Alembic** — NO `down -v`. Your data stays.

## What's new
- **Light mode** — warm-paper light theme (not stark white; keeps the ma. feel).
  Toggle in Settings → theme. Smooth cross-fade.
- **Collapse actually reflows** — hiding the sidebar/task panel now shrinks the
  grid track to 0 and the calendar **grows to fill** (animated), instead of
  leaving a gap.
- **Animations** — modals pop, cards lift on hover, blocks/transitions ease,
  theme changes cross-fade.
- **Real settings panel** — appearance (theme, accent color, density, font
  size, default view) + study prefs (awake hours, min block, cushion) +
  calendar prefs (week start) all in one place.

## Apply (no reset — Alembic migrates)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4c kit
docker compose build --no-cache hive-api && docker compose up -d
docker compose logs hive-api --tail 8   # should show alembic applying 0002
```
Normal refresh. On boot, migration `0002_appearance` adds the new settings
columns automatically.

## Still ahead
- Drag mechanics tuning (you flagged — next).
- Calibration engine + Ollama; onboarding wizard; grades/analytics/syllabus.
