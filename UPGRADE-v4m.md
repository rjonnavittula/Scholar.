# scholar. v4m — settings, rebuilt from scratch (settings only)

No schema change → **no DB reset.** This release changes ONLY the settings panel.

## What changed
The settings system was rebuilt completely (not patched) as the layout you
picked — **left rail + single-scroll sections**:
- **Left rail** switches between Term / Personalization / Appearance /
  Notifications / Account, with an animated crossfade between sections.
- **Inside** each section, fields flow as a comfortable single scroll: grouped
  cards with section sub-headers, one labelled row per setting (label + hint on
  the left, control on the right), generous spacing. No more cramped column.
- Proper proportions: 180px rail, wide content that fills the card.
- Sticky save/cancel footer; the card morphs open with a scale+fade.
- All controls wired: term dates, timezones (country→zone), study-planning
  numbers, week start, default view, theme/density/font/accent, awake-time
  widget (visual day bars + tap-to-edit + drag + presets), display name,
  mint-key.

Old settings CSS and the three old settings functions were removed entirely —
this is a clean implementation, not another layer.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4m kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh.

## Please check just the settings this round
- Open settings (gear). It should be a wide card, rail on the left.
- Click through all five sections — each should glide in, fields readable and
  spaced, controls filling the right side.
- Change something in each (e.g. accent, week start, a term date, awake hours),
  hit save, reopen — it should persist.
- Everything else (calendar, etc.) is intentionally untouched this round.
