# scholar. v4d — Shovel-style settings panel

Schema change handled by **Alembic** (migration 0003) — NO `down -v`.

## What's new
- **Settings rebuilt as a left-nav panel** (like Shovel): sections for
  **Term / Personalization / Appearance / Notifications / Account**.
  - **Term** — country, school timezone, your home timezone, term dates.
  - **Personalization** — study planning (min block, start-ahead, cushion %),
    week start, default view, awake hours.
  - **Appearance** — theme (dark/light), density, font size, accent color.
  - **Notifications** — stubbed (placeholders; needs a notification service —
    marked "coming soon").
  - **Account** — display name + mint-a-new-API-key button.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4d kit
docker compose build --no-cache hive-api && docker compose up -d
docker compose logs hive-api --tail 6   # alembic applies 0003
```
Normal refresh.

## Next
- **SP-inspired features** (agreed): Pomodoro mode on the timer, sub-tasks,
  repeating tasks — their own round (sub-tasks & repeating each add a small
  Alembic migration, no reset).
- Then: drag-mechanics tuning, calibration engine, onboarding wizard.
