#!/usr/bin/env bash
# fix-v3a.sh — three polish fixes:
#   1) hour-label vertical alignment (labels sit on their gridlines)
#   2) duration field accepts minutes OR hours
#   3) due dates DISPLAY in your school zone (stored UTC, shown ET)
# Run from inside hive-tasks/:  bash fix-v3a.sh
set -euo pipefail
[ -f webui/css/app.css ] || { echo "run from inside hive-tasks/"; exit 1; }

# ── FIX 1: hour labels positioned absolutely on the gridlines ───────────────
python3 - <<'PY'
import pathlib
# CSS: make gutter a positioning context; labels absolute at h*hourH
css = pathlib.Path("webui/css/app.css")
c = css.read_text()
c = c.replace(
  ".gutter-cell { grid-row:2; grid-column:1;\n  position:sticky; left:0; background:var(--bg); z-index:4;\n  height:calc(24 * var(--hourH)); }",
  ".gutter-cell { grid-row:2; grid-column:1;\n  position:sticky; left:0; background:var(--bg); z-index:4;\n  height:calc(24 * var(--hourH)); }")
c = c.replace(
  ".hour-label { height:var(--hourH); font-size:10px; color:var(--faint);\n  text-align:right; padding-right:6px; transform:translateY(-6px); }",
  ".hour-label { position:absolute; right:6px; font-size:10px; color:var(--faint);\n  transform:translateY(-50%); }")
css.write_text(c)
print("  FIX1 css: ok")

# JS: emit hour labels with an absolute top, and make the gutter relative
cal = pathlib.Path("webui/js/calendar.js")
j = cal.read_text()
j = j.replace(
  "    html += '<div class=\"gutter-cell\">';\n    for (let h = 0; h < 24; h++) html += `<div class=\"hour-label\">${pad(h)}:00</div>`;\n    html += '</div>';",
  "    html += '<div class=\"gutter-cell\" style=\"position:sticky;\">';\n    for (let h = 0; h < 24; h++) html += `<div class=\"hour-label\" style=\"top:${h * HOUR}px\">${pad(h)}:00</div>`;\n    html += '</div>';")
cal.write_text(j)
print("  FIX1 js: ok")
PY

# gutter needs position context for absolute labels
grep -q ".gutter-cell { position:sticky" webui/css/app.css && \
  python3 - <<'PY'
import pathlib
css = pathlib.Path("webui/css/app.css"); c = css.read_text()
# ensure the gutter establishes a positioning context (sticky already does, but
# absolute children resolve against nearest positioned ancestor — sticky counts)
if "/* gutter-pos */" not in c:
    c += "\n/* gutter-pos */\n.gutter-cell { position:sticky; } /* abs hour-labels resolve here */\n"
    css.write_text(c)
print("  FIX1 gutter-pos: ok")
PY

# ── FIX 2: duration as number + min/hrs unit ────────────────────────────────
python3 - <<'PY'
import pathlib
js = pathlib.Path("webui/js/app.js"); s = js.read_text()

# modal field: number input + unit select, defaulting to whichever reads cleaner
old = '''        <div><label>minutes needed</label><input id="m-need" type="number" min="0" step="15"
          value="${t?.time_needed_min ?? 60}" /></div>'''
new = '''        <div><label>time needed</label>
          <div class="dur-field">
            <input id="m-need" type="number" min="0" step="${(t?.time_needed_min ?? 60) % 60 === 0 ? 1 : 15}"
              value="${(t?.time_needed_min ?? 60) % 60 === 0 ? (t?.time_needed_min ?? 60) / 60 : (t?.time_needed_min ?? 60)}" />
            <select id="m-need-unit">
              <option value="hrs" ${(t?.time_needed_min ?? 60) % 60 === 0 ? 'selected' : ''}>hrs</option>
              <option value="min" ${(t?.time_needed_min ?? 60) % 60 !== 0 ? 'selected' : ''}>min</option>
            </select>
          </div></div>'''
assert old in s, "minutes field not found"
s = s.replace(old, new)

# save: convert by unit
s = s.replace(
  "          time_needed_min: +ovEl.querySelector('#m-need').value || 60,",
  "          time_needed_min: (() => { const v = +ovEl.querySelector('#m-need').value || 0;\n            return ovEl.querySelector('#m-need-unit').value === 'hrs' ? Math.round(v * 60) : v; })() || 60,")

js.write_text(s)
print("  FIX2: ok")
PY

# small CSS for the duration field
grep -q ".dur-field" webui/css/app.css || cat >> webui/css/app.css <<'CSS'

/* duration number + unit */
.dur-field { display:flex; gap:6px; }
.dur-field input { flex:1; min-width:0; }
.dur-field select { width:74px; flex:none; }
CSS
echo "  FIX2 css: ok"

# ── FIX 3: due dates display in the school zone (stored UTC) ────────────────
python3 - <<'PY'
import pathlib
# add a tz-format helper to api.js and use it in panel + app where due shows.
api = pathlib.Path("webui/js/api.js"); a = api.read_text()
if "fmtInZone" not in a:
    a = a.replace(
      "  return {\n    setKey, hasKey: () => !!KEY,",
      """  // ---- timezone display helpers ----
  // The API returns UTC instants (…+00:00 / Z). Render them in a named zone.
  function fmtInZone(iso, tz, opts) {
    if (!iso) return '';
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return new Intl.DateTimeFormat('en-US', { timeZone: tz, ...opts }).format(d);
  }
  function dayInZone(iso, tz) {
    // YYYY-MM-DD as seen in tz
    const parts = fmtInZone(iso, tz, { year: 'numeric', month: '2-digit', day: '2-digit' });
    const [m, d, y] = parts.split('/');
    return `${y}-${m}-${d}`;
  }

  return {
    setKey, hasKey: () => !!KEY, fmtInZone, dayInZone,""")
    api.write_text(a)
    print("  FIX3 api helpers: ok")

# panel.js: use school tz for due display + bucketing
pan = pathlib.Path("webui/js/panel.js"); p = pan.read_text()
p = p.replace(
  "${t.due_at ? `<span>due ${t.due_at.slice(5, 10)} ${t.due_at.slice(11, 16)}</span>` : ''}",
  "${t.due_at ? `<span>due ${Api.fmtInZone(t.due_at, SCHOOL_TZ(), { month: '2-digit', day: '2-digit' })} ${Api.fmtInZone(t.due_at, SCHOOL_TZ(), { hour: '2-digit', minute: '2-digit', hour12: false })}</span>` : ''}")
# bucket by school-zone day, not raw slice
p = p.replace(
  "      const lab = bucketLabel(t.due_at.slice(0, 10), todayIso);",
  "      const lab = bucketLabel(Api.dayInZone(t.due_at, SCHOOL_TZ()), todayIso);")
# overdue/future compare already uses new Date(due) which is correct (UTC instant)
# add a SCHOOL_TZ accessor pulling from state
if "function SCHOOL_TZ" not in p:
    p = p.replace(
      "/* panel.js — the right rail: Overdue / Due buckets / No due date. */",
      "/* panel.js — the right rail: Overdue / Due buckets / No due date. */\nfunction SCHOOL_TZ() { return (window.__S && window.__S.settings && window.__S.settings.school_tz) || 'America/New_York'; }")
pan.write_text(p)
print("  FIX3 panel: ok")

# expose state for SCHOOL_TZ + show task-modal default time note. app.js: stash S on window.
app = pathlib.Path("webui/js/app.js"); s = app.read_text()
if "window.__S = S;" not in s:
    s = s.replace("  async function loadAll() {", "  window.__S = S;\n  async function loadAll() {")
# app.js task-list inline due also uses school zone
s = s.replace(
  "${t.due_at ? 'due ' + t.due_at.slice(0,10) : 'unscheduled'}",
  "${t.due_at ? 'due ' + Api.dayInZone(t.due_at, (S.settings.school_tz || 'America/New_York')) : 'unscheduled'}")
app.write_text(s)
print("  FIX3 app: ok")
PY

echo "done. rebuild: docker compose build --no-cache hive-api && docker compose up -d"
