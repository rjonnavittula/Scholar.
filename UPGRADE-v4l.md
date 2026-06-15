# scholar. v4l — FullCalendar fixes + settings redesign + theme toggle

No schema change → **no DB reset.** Still loads FullCalendar from CDN.

## Calendar (FullCalendar, bugs fixed)
- **Drag now works** — task cards use FullCalendar's official `Draggable`, and
  drops are handled by `eventReceive` (the documented, reliable path). Drag a
  card onto the grid to plan it; drag a block to move; grab top/bottom to resize.
- **Prev / next navigate properly** — and they're **view-aware**: in Month view
  they jump a month, in Week/Next-N they jump that many days.
- **Time-passed shading** — past days and today's elapsed hours are tinted
  (background events), matching what you had before.
- **Day tab hidden on desktop** (kept for phones < 768px) — Week view covers it.

## Settings — redesigned (C + B hybrid)
- Keeps the **left rail** for sections (Term / Personalization / Appearance /
  Notifications / Account)…
- …but **inside** each section, fields now flow as a comfortable **single
  scroll** with breathing room (no more cramped grid). Proportions fixed:
  narrower rail, wide content that fills the space.
- Still morphs open with animation.

## Sidebar
- **Dark / light toggle** added above the gear (☽ / ☀) — one click, persists.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4l kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh. First load needs internet for the FullCalendar CDN.

## Watch on first run
- Drag a task card onto the calendar → it should plan a block there.
- Prev/next arrows should move the calendar (and Month jumps by month).
- Past time should look dimmer.
- Theme toggle (☽) in the sidebar should flip light/dark instantly.
- If the calendar says "library failed to load", the CDN was blocked — tell me
  and I'll bundle FullCalendar into the kit locally.
