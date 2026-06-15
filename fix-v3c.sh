#!/usr/bin/env bash
# fix-v3c.sh — fix the few-pixel grid offset / 00:00 clipping the RIGHT way:
# remove the broken padding hack and bake a uniform top inset into y() so every
# absolutely-positioned element (lines, labels, blocks, flags, now-line) shares
# one origin with breathing room at the top.
set -euo pipefail
[ -f webui/js/calendar.js ] || { echo "run from inside hive-tasks/"; exit 1; }

# 1) remove the padding-top hack from the previous patch
python3 - <<'PY'
import pathlib
css = pathlib.Path("webui/css/app.css"); c = css.read_text()
c = c.replace(".gutter-cell { grid-row:2; grid-column:1; padding-top:var(--calPadTop);",
              ".gutter-cell { grid-row:2; grid-column:1;")
c = c.replace(".day-col { position:relative; border-left:1px solid var(--line); padding-top:var(--calPadTop);",
              ".day-col { position:relative; border-left:1px solid var(--line);")
# keep the label centered on its line; add small height so the grid body has
# room for the inset (24h + inset)
c = c.replace("grid-template-rows:var(--calHeadH) calc(24 * var(--hourH));",
              "grid-template-rows:var(--calHeadH) calc(24 * var(--hourH) + var(--calPadTop) * 2);")
css.write_text(c)
print("  removed padding hack, grew body row for inset: ok")
PY

# 2) bake the inset into y() so EVERYTHING shifts together
python3 - <<'PY'
import pathlib
js = pathlib.Path("webui/js/calendar.js"); s = js.read_text()
# add PAD const and fold it into y()
s = s.replace(
  "  const HOUR = 46;                       // px per hour — matches --hourH",
  "  const HOUR = 46;                       // px per hour — matches --hourH\n  const PAD = 10;                        // top inset — matches --calPadTop")
s = s.replace(
  "  const y = (min) => (min / 60) * HOUR;",
  "  const y = (min) => (min / 60) * HOUR + PAD;   // uniform top inset for all placement")
# labels + lines must also route through y() so they share the inset origin
s = s.replace(
  'for (let h = 0; h < 24; h++) html += `<div class="hour-label" style="top:${h * HOUR}px">${pad(h)}:00</div>`;',
  'for (let h = 0; h < 24; h++) html += `<div class="hour-label" style="top:${y(h * 60)}px">${pad(h)}:00</div>`;')
s = s.replace(
  'for (let h = 1; h < 24; h++) html += `<div class="hour-line" style="top:${h * HOUR}px"></div>`;',
  'for (let h = 1; h < 24; h++) html += `<div class="hour-line" style="top:${y(h * 60)}px"></div>`;')
# the day-col/gutter explicit height must include the inset too
s = s.replace(
  'style="height:${24 * HOUR}px">',
  'style="height:${24 * HOUR + PAD * 2}px">')
js.write_text(s)
print("  y() inset applied: ok")
PY

# 3) bump cache-bust
python3 - <<'PY'
import pathlib, re, time
h = pathlib.Path("webui/index.html"); s = h.read_text(); v = str(int(time.time()))
s = re.sub(r'(\.(css|js))(\?v=\d+)?"', rf'\1?v={v}"', s)
h.write_text(s); print(f"  cache-bust: ?v={v}")
PY

echo "done. rebuild: docker compose build --no-cache hive-api && docker compose up -d"
