#!/usr/bin/env bash
# fix-v4a-dur.sh — replace the time-needed number+dropdown with a Shovel-style
# h/m stepper (tappable +/- on hours and minutes, with rollover).
set -euo pipefail
[ -f webui/js/app.js ] || { echo "run from inside hive-tasks/"; exit 1; }

python3 - <<'PY'
import pathlib
s = pathlib.Path("webui/js/app.js").read_text()

old = '''        <div><label>time needed</label>
          <div class="dur-field">
            <input id="m-need" type="number" min="0" step="${(t?.time_needed_min ?? 60) % 60 === 0 ? 1 : 15}"
              value="${(t?.time_needed_min ?? 60) % 60 === 0 ? (t?.time_needed_min ?? 60) / 60 : (t?.time_needed_min ?? 60)}" />
            <select id="m-need-unit">
              <option value="hrs" ${(t?.time_needed_min ?? 60) % 60 === 0 ? 'selected' : ''}>hrs</option>
              <option value="min" ${(t?.time_needed_min ?? 60) % 60 !== 0 ? 'selected' : ''}>min</option>
            </select>
          </div></div>'''

new = '''        <div><label>time needed</label>
          <div class="stepper" id="m-need" data-min="${t?.time_needed_min ?? 60}">
            <div class="seg">
              <button type="button" class="st-up" data-k="h">\\u2039</button>
              <div class="val"><span class="st-h">${Math.floor((t?.time_needed_min ?? 60) / 60)}</span><i>h</i></div>
              <button type="button" class="st-dn" data-k="h">\\u203A</button>
            </div>
            <div class="seg">
              <button type="button" class="st-up" data-k="m">\\u2039</button>
              <div class="val"><span class="st-m">${(t?.time_needed_min ?? 60) % 60}</span><i>m</i></div>
              <button type="button" class="st-dn" data-k="m">\\u203A</button>
            </div>
          </div></div>'''
assert old in s, "duration field not found (already patched?)"
s = s.replace(old, new)

# save: read minutes from the stepper's data-min
s = s.replace(
  '''          time_needed_min: (() => { const v = +ovEl.querySelector('#m-need').value || 0;
            return ovEl.querySelector('#m-need-unit').value === 'hrs' ? Math.round(v * 60) : v; })() || 60,''',
  "          time_needed_min: +ovEl.querySelector('#m-need').dataset.min || 60,")

# wire the stepper after the modal builds (alongside initTzPicker call)
s = s.replace(
  "    initTzPicker(ov, t?.due_tz || S.settings.school_tz || 'America/New_York');",
  "    initTzPicker(ov, t?.due_tz || S.settings.school_tz || 'America/New_York');\n    wireStepper(ov.querySelector('#m-need'));")

# add the wireStepper helper near initTzPicker
s = s.replace(
  "  function detectCountry() {",
  """  function wireStepper(el) {
    if (!el) return;
    const draw = () => {
      const m = +el.dataset.min;
      el.querySelector('.st-h').textContent = Math.floor(m / 60);
      el.querySelector('.st-m').textContent = m % 60;
    };
    const bump = (k, dir) => {
      let m = +el.dataset.min;
      m += (k === 'h' ? 60 : 5) * dir;
      m = Math.max(0, Math.min(24 * 60, m));   // 0 .. 24h
      el.dataset.min = m;
      draw();
    };
    // chevrons: \\u2039 (up button) increments, \\u203A (down) decrements
    for (const b of el.querySelectorAll('.st-up')) b.onclick = () => bump(b.dataset.k, +1);
    for (const b of el.querySelectorAll('.st-dn')) b.onclick = () => bump(b.dataset.k, -1);
    draw();
  }

  function detectCountry() {""")

pathlib.Path("webui/js/app.js").write_text(s)
print("stepper markup + logic: ok")
PY

# stepper CSS
grep -q ".stepper {" webui/css/app.css || cat >> webui/css/app.css <<'CSS'

/* h/m stepper (Shovel-style) */
.stepper { display:flex; gap:10px; }
.stepper .seg { display:flex; align-items:center; gap:8px; background:var(--input);
  border:1px solid var(--line); border-radius:var(--pill); padding:4px 8px; }
.stepper .seg .val { min-width:38px; text-align:center; }
.stepper .seg .val span { font-size:18px; font-family:var(--serif); }
.stepper .seg .val i { color:var(--muted); font-style:normal; font-size:11px; margin-left:1px; }
.stepper .seg button { background:none; border:none; color:var(--muted);
  font-size:20px; line-height:1; padding:2px 6px; cursor:pointer;
  transform:rotate(90deg); }
.stepper .seg button:hover { color:var(--accent); }
.stepper .seg .st-up { transform:rotate(90deg); }   /* ‹ -> points up */
.stepper .seg .st-dn { transform:rotate(-90deg); }  /* › -> points down */
CSS
echo "stepper css: ok"

# cache-bust
python3 - <<'PY'
import pathlib, re, time
h = pathlib.Path("webui/index.html"); s = h.read_text(); v = str(int(time.time()))
s = re.sub(r'(\.(css|js))(\?v=\d+)?"', rf'\1?v={v}"', s); h.write_text(s)
print(f"cache-bust ?v={v}")
PY
echo done
