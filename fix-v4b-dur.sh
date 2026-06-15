#!/usr/bin/env bash
# fix-v4a-dur2.sh — make time-needed TYPEABLE (Shovel-style): editable h & m
# number fields you can type into, with small up/down arrows for fine-tuning.
# Clamp + rollover on input/blur. Replaces the toggle-only stepper.
set -euo pipefail
[ -f webui/js/app.js ] || { echo "run from inside hive-tasks/"; exit 1; }

python3 - <<'PY'
import pathlib, re
s = pathlib.Path("webui/js/app.js").read_text()

# --- replace the stepper markup with typeable inputs ---
start = s.index('        <div><label>time needed</label>')
end = s.index('          </div></div>', start) + len('          </div></div>')
block = s[start:end]

new = '''        <div><label>time needed</label>
          <div class="dur" id="m-need" data-min="${t?.time_needed_min ?? 60}">
            <div class="dseg">
              <button type="button" class="dstep" data-k="h" data-d="1">\\u25B2</button>
              <input class="dh" type="text" inputmode="numeric" maxlength="2"
                value="${Math.floor((t?.time_needed_min ?? 60) / 60)}" /><i>h</i>
              <button type="button" class="dstep" data-k="h" data-d="-1">\\u25BC</button>
            </div>
            <div class="dseg">
              <button type="button" class="dstep" data-k="m" data-d="1">\\u25B2</button>
              <input class="dm" type="text" inputmode="numeric" maxlength="2"
                value="${String((t?.time_needed_min ?? 60) % 60).padStart(2, '0')}" /><i>m</i>
              <button type="button" class="dstep" data-k="m" data-d="-1">\\u25BC</button>
            </div>
          </div></div>'''
s = s[:start] + new + s[end:]

# --- wireStepper -> read from inputs, support typing + arrows ---
old_wire = s[s.index("  function wireStepper(el) {"):s.index("  function detectCountry() {")]
new_wire = '''  function wireStepper(el) {
    if (!el) return;
    const hI = el.querySelector('.dh'), mI = el.querySelector('.dm');
    const sync = () => {
      let h = Math.max(0, Math.min(24, parseInt(hI.value || '0', 10) || 0));
      let m = Math.max(0, Math.min(59, parseInt(mI.value || '0', 10) || 0));
      let total = h * 60 + m;
      if (total > 1440) total = 1440;
      el.dataset.min = total;
    };
    const redraw = () => {
      const t = +el.dataset.min;
      hI.value = Math.floor(t / 60);
      mI.value = String(t % 60).padStart(2, '0');
    };
    // typing: keep digits only, sync live; normalize on blur
    [hI, mI].forEach((inp) => {
      inp.addEventListener('input', () => {
        inp.value = inp.value.replace(/[^0-9]/g, '').slice(0, 2);
        sync();
      });
      inp.addEventListener('blur', () => { sync(); redraw(); });
      inp.addEventListener('focus', () => inp.select());
    });
    // arrows: hours \\u00b11, minutes \\u00b15 with rollover
    for (const b of el.querySelectorAll('.dstep')) {
      b.onclick = () => {
        sync();
        let total = +el.dataset.min;
        total += (b.dataset.k === 'h' ? 60 : 5) * (+b.dataset.d);
        el.dataset.min = Math.max(0, Math.min(1440, total));
        redraw();
      };
    }
    sync();
  }

'''
s = s.replace(old_wire, new_wire)

pathlib.Path("webui/js/app.js").write_text(s)
print("typeable duration field: ok")
PY

# --- CSS: replace stepper styles with the typeable .dur layout ---
python3 - <<'PY'
import pathlib, re
css = pathlib.Path("webui/css/app.css").read_text()
# drop old stepper block
i = css.index("/* h/m stepper (Shovel-style) */")
j = css.index("CSS", i) if "CSS" in css[i:] else len(css)
# old block runs to end of those rules; find the next blank-line-delimited section end
# simpler: cut from marker to the next "/*" comment after it
nxt = css.find("/*", i + 5)
css = css[:i] + (css[nxt:] if nxt != -1 else "")
css += """
/* typeable h/m duration */
.dur { display:flex; gap:12px; }
.dur .dseg { display:flex; flex-direction:column; align-items:center;
  background:var(--input); border:1px solid var(--line); border-radius:14px;
  padding:4px 10px 6px; position:relative; }
.dur .dseg input { width:42px; text-align:center; background:none; border:none;
  color:var(--fg); font-family:var(--serif); font-size:22px; padding:0; }
.dur .dseg input:focus { outline:none; }
.dur .dseg i { position:absolute; right:8px; bottom:9px; color:var(--muted);
  font-style:normal; font-size:11px; pointer-events:none; }
.dur .dstep { background:none; border:none; color:var(--faint); cursor:pointer;
  font-size:9px; line-height:1; padding:1px; }
.dur .dstep:hover { color:var(--accent); }
"""
pathlib.Path("webui/css/app.css").write_text(css)
print("dur css: ok")
PY

# cache-bust
python3 - <<'PY'
import pathlib, re, time
h = pathlib.Path("webui/index.html"); s = h.read_text(); v = str(int(time.time()))
s = re.sub(r'(\.(css|js))(\?v=\d+)?"', rf'\1?v={v}"', s); h.write_text(s)
print(f"cache-bust ?v={v}")
PY
echo done
