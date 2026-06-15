#!/usr/bin/env bash
# fix-v3b.sh — (1) stop 00:00 hour-label clipping, (2) place due-flags and
# planned blocks at the correct LOCAL time (convert UTC -> zone), not raw UTC.
set -euo pipefail
[ -f webui/css/app.css ] || { echo "run from inside hive-tasks/"; exit 1; }

# ── FIX 1: give the grid body top breathing room so hour 0 isn't clipped ────
python3 - <<'PY'
import pathlib
css = pathlib.Path("webui/css/app.css"); c = css.read_text()
# pad the top of day columns + gutter by half a label, and start hour lines
# from that offset. Cleanest: add padding-top to the scroll content via the
# grid rows — bump the body row start with a transparent spacer is messy, so
# instead nudge labels: keep absolute, but the FIRST one (top:0) shouldn't be
# pulled above the viewport. Add 9px top padding to gutter + day-col and shift
# all absolutely-positioned children down by the same 9px via a CSS var.
if "--calPadTop" not in c:
    c = c.replace("--hourH:46px; --gutter:52px; --calHeadH:74px;",
                  "--hourH:46px; --gutter:52px; --calHeadH:74px; --calPadTop:10px;")
# add the pad to gutter + day columns
c = c.replace(
  ".gutter-cell { grid-row:2; grid-column:1;",
  ".gutter-cell { grid-row:2; grid-column:1; padding-top:var(--calPadTop);")
c = c.replace(
  ".day-col { position:relative; border-left:1px solid var(--line);",
  ".day-col { position:relative; border-left:1px solid var(--line); padding-top:var(--calPadTop);")
css.write_text(c)
print("  FIX1 css pad: ok")
PY

# ── FIX 2: zone-correct placement in calendar.js ────────────────────────────
python3 - <<'PY'
import pathlib
js = pathlib.Path("webui/js/calendar.js"); s = js.read_text()

# helper: given a UTC iso + tz, return minutes-of-day in that zone, and the
# local YYYY-MM-DD. Insert near the top of the IIFE.
if "function zoneMin" not in s:
    s = s.replace(
      "  function mount(el, state, handlers) { root = el; S = state; H = handlers; }",
      """  function tz() {
    const st = (S && S.settings) || {};
    return { home: st.home_tz || 'America/New_York', school: st.school_tz || 'America/New_York' };
  }
  function asUtc(iso) { return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z'); }
  function zoneMin(iso, zoneName) {
    // minutes-of-day for a UTC instant as seen in zoneName
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: zoneName, hour: '2-digit',
      minute: '2-digit', hour12: false }).formatToParts(asUtc(iso));
    const h = +parts.find((p) => p.type === 'hour').value % 24;
    const m = +parts.find((p) => p.type === 'minute').value;
    return h * 60 + m;
  }
  function zoneDay(iso, zoneName) {
    const p = new Intl.DateTimeFormat('en-US', { timeZone: zoneName, year: 'numeric',
      month: '2-digit', day: '2-digit' }).format(asUtc(iso));
    const [mm, dd, yy] = p.split('/');
    return `${yy}-${mm}-${dd}`;
  }

  function mount(el, state, handlers) { root = el; S = state; H = handlers; }""")

# planned blocks: match the day in HOME zone, place by HOME-zone minutes
s = s.replace(
  "      for (const p of S.planned.filter((x) => x.start_at.slice(0, 10) === iso)) {\n        const t = taskOf(p.task_id) || {};\n        const c = courseOf(t);\n        const sMin = hmToMin(p.start_at.slice(11, 16));\n        const eMin = hmToMin(p.end_at.slice(11, 16)) || 1440;",
  "      for (const p of S.planned.filter((x) => zoneDay(x.start_at, tz().home) === iso)) {\n        const t = taskOf(p.task_id) || {};\n        const c = courseOf(t);\n        const sMin = zoneMin(p.start_at, tz().home);\n        const eMin = zoneMin(p.end_at, tz().home) || 1440;")

# due flags: match + place in SCHOOL zone, and label with tz abbr
s = s.replace(
  "      for (const t of S.tasks.filter((x) => x.status !== 'done'\n          && x.due_at && x.due_at.slice(0, 10) === iso)) {\n        const m = hmToMin(t.due_at.slice(11, 16));",
  "      for (const t of S.tasks.filter((x) => x.status !== 'done'\n          && x.due_at && zoneDay(x.due_at, tz().school) === iso)) {\n        const m = zoneMin(t.due_at, tz().school);")

js.write_text(s)
print("  FIX2 calendar zone placement: ok")
PY

# bump asset cache-bust so the browser can't serve stale UI (belt + suspenders)
python3 - <<'PY'
import pathlib, time
html = pathlib.Path("webui/index.html"); h = html.read_text()
v = str(int(time.time()))
import re
h = re.sub(r'(href="css/app\.css)(\?v=\d+)?"', f'\\1?v={v}"', h)
h = re.sub(r'(src="js/(\w+)\.js)(\?v=\d+)?"', f'\\1?v={v}"', h)
html.write_text(h)
print(f"  cache-bust applied: ?v={v}")
PY

echo "done. rebuild: docker compose build --no-cache hive-api && docker compose up -d"
