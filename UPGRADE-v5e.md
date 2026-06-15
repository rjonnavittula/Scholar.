# scholar. v5e — activities look right + hover-only scrollbars

**No schema change → no DB reset.** Frontend only (calendar.js + CSS).

## What changed
- **Activities on the calendar are now real colored blocks**, not the faint grey
  ghost text. Each renders in its own colour — a subtle tinted fill, a solid
  colour border (thicker on the left, Shovel-style), and readable colour text,
  with its time shown. Still non-draggable (they're routines, not tasks), so
  they read as the backdrop your tasks get planned around — just visible now.
- **Scrollbars are hover-only.** The thumb is invisible until you hover the
  scrollable area, then fades in (and tints to the accent when you grab it).
  Applies everywhere; Firefox uses the same reveal-on-hover.

## Apply
Either the new git flow (see chat) or the zip:
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v5e kit
docker compose build --no-cache hive-api && docker compose up -d
```
Hard-refresh.

## Still open
- The activity *times* themselves (lunch at ~3:40 AM) still look like a stored
  time / timezone issue — separate from this rendering fix. Say the word and I
  trace the activity save path.
- Next queued: v5f course hub, then grades + syllabus; streak redesign.
