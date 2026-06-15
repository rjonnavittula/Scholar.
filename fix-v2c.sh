#!/usr/bin/env bash
# fix-v2c.sh — calendar layout + scroll, click-to-edit, timezone.
# Run from inside hive-tasks/:  bash fix-v2c.sh "America/New_York"
#   (pass your IANA tz; defaults to America/New_York)
set -euo pipefail
[ -f webui/css/app.css ] || { echo "run me from inside hive-tasks/"; exit 1; }
TZNAME="${1:-America/New_York}"

# ── FIX A: layout + scroll ─────────────────────────────────────────────────
# .main must be allowed to shrink (min-height:0) so .calendar can own a
# bounded, scrollable height inside the grid cell. And the calendar grid's
# header row must be sticky as a unit so columns line up under it.
python3 - <<'PY'
import pathlib
p = pathlib.Path("webui/css/app.css")
css = p.read_text()

css = css.replace(
  ".main { display:flex; flex-direction:column; min-width:0; }",
  ".main { display:flex; flex-direction:column; min-width:0; min-height:0; height:100vh; }")

css = css.replace(
  ".calendar { flex:1; overflow:auto; position:relative; }",
  ".calendar { flex:1; min-height:0; overflow-y:auto; overflow-x:auto; position:relative; }")

# header cells: keep sticky, but ensure the whole header row shares one origin
# and the day columns/gutter start at the same y. Setting the gutter + columns
# to align-self:start inside row 2 keeps them flush.
css = css.replace(
  ".cal-grid > .gutter-cell, .cal-grid > .day-col { grid-row:2; }",
  ".cal-grid > .gutter-cell, .cal-grid > .day-col { grid-row:2; align-self:start; }")

p.write_text(css)
print("  FIX A layout/scroll: ok")
PY

# ── FIX B: click course/activity → open the same edit modal ────────────────
python3 - <<'PY'
import pathlib
p = pathlib.Path("webui/js/app.js")
js = p.read_text()

# --- courses: make the row clickable (but not when hitting the ✕) ---
js = js.replace(
  '      <div class="side-item" data-cid="${c.id}">',
  '      <div class="side-item clickable" data-edit-course="${c.id}">')

# --- activities: row carries the group ids so edit can prefill ---
js = js.replace(
  '''      <div class="side-item">
        <span class="dot" style="background:${g.color}"></span>
        <span class="nm">${esc(g.title)}</span>
        <span class="meta">${dayAbbr(g.days)} ${minToHM(g.start_min)}</span>
        <button class="x" data-del-act="${g.ids.join(',')}">✕</button>
      </div>''',
  '''      <div class="side-item clickable" data-edit-act="${g.ids.join(',')}"
           data-title="${esc(g.title)}" data-color="${g.color}"
           data-days="${g.days.join(',')}" data-s="${g.start_min}" data-e="${g.end_min}">
        <span class="dot" style="background:${g.color}"></span>
        <span class="nm">${esc(g.title)}</span>
        <span class="meta">${dayAbbr(g.days)} ${minToHM(g.start_min)}</span>
        <button class="x" data-del-act="${g.ids.join(',')}">✕</button>
      </div>''')

# --- wire the click handlers (after the existing delete wiring) ---
anchor = """    for (const b of document.querySelectorAll('[data-del-act]'))
      b.onclick = async () => {
        const ids = b.dataset.delAct.split(',');
        await Promise.all(ids.map((id) => Api.del('/activities/' + id)));
        loadAll();
      };"""
add = anchor + """

    for (const row of document.querySelectorAll('[data-edit-course]'))
      row.onclick = (e) => { if (e.target.closest('.x')) return;
        const c = S.courses.find((x) => x.id === +row.dataset.editCourse);
        if (c) courseModal(c); };
    for (const row of document.querySelectorAll('[data-edit-act]'))
      row.onclick = (e) => { if (e.target.closest('.x')) return;
        activityModal({
          ids: row.dataset.editAct.split(',').map(Number),
          title: row.dataset.title, color: row.dataset.color,
          days: row.dataset.days.split(',').map(Number),
          start_min: +row.dataset.s, end_min: +row.dataset.e,
        }); };"""
assert anchor in js, "delete-act wiring not found"
js = js.replace(anchor, add)

# --- courseModal: accept an existing course for editing ---
js = js.replace(
  """  function courseModal() {
    modal(`
      <h2>new course</h2>
      <div class="frow"><label>name</label><input id="m-name" placeholder="CMPEN 331" /></div>
      <div class="frow"><label>color</label>${swatchHtml(PALETTE[S.courses.length % PALETTE.length])}</div>
      ${ACTIONS('add')}`,
      async (act, ov) => {
        if (act !== 'save') return;
        const nm = ov.querySelector('#m-name').value.trim() || 'course';
        await Api.post('/courses', {
          name: nm,
          color: ov.querySelector('.swatch.sel')?.dataset.c || PALETTE[0],
        });
        await loadAll();
        toast(`added course \\u00b7 ${nm}`);
      });
    wireSwatches($('modal-root'));
  }""",
  """  function courseModal(course) {
    const sel = course?.color || PALETTE[S.courses.length % PALETTE.length];
    modal(`
      <h2>${course ? 'edit course' : 'new course'}</h2>
      <div class="frow"><label>name</label><input id="m-name" value="${esc(course?.name || '')}" placeholder="CMPEN 331" /></div>
      <div class="frow"><label>color</label>${swatchHtml(sel)}</div>
      ${course ? '<div class="actions left"><button class="ghost danger-btn" data-m="del">delete</button></div>' : ''}
      ${ACTIONS(course ? 'save' : 'add')}`,
      async (act, ov) => {
        if (act === 'del') { await Api.del('/courses/' + course.id); await loadAll(); return toast('course deleted'); }
        if (act !== 'save') return;
        const nm = ov.querySelector('#m-name').value.trim() || 'course';
        const color = ov.querySelector('.swatch.sel')?.dataset.c || PALETTE[0];
        if (course) await Api.patch('/courses/' + course.id, { name: nm, color });
        else await Api.post('/courses', { name: nm, color });
        await loadAll();
        toast(`${course ? 'updated' : 'added'} course \\u00b7 ${nm}`);
      });
    wireSwatches($('modal-root'));
  }""")

# --- activityModal: accept an existing grouped activity for editing ---
js = js.replace(
  """  function activityModal() {
    const { ov } = modal(`
      <h2>new activity</h2>
      <div class="frow"><label>title</label><input id="m-name" placeholder="CMPEN 331 lecture / lunch / workout" /></div>
      <div class="frow"><label>days</label>
        <div class="daypick">${DAYS.map((d, i) => `<button data-d="${i}">${d}</button>`).join('')}</div></div>
      <div class="frow">
        <div><label>start</label><input id="m-s" type="time" value="${nowHM()}" /></div>
        <div><label>end</label><input id="m-e" type="time" value="${plusHM(50)}" /></div>
      </div>
      <div class="frow"><label>color</label>${swatchHtml('#5F6B5A')}</div>
      ${ACTIONS('block it')}`,
      async (act, ovEl) => {
        if (act !== 'save') return;
        const days = [...ovEl.querySelectorAll('.daypick button.sel')].map((b) => +b.dataset.d);
        const s = hmToMin(ovEl.querySelector('#m-s').value);
        const e = hmToMin(ovEl.querySelector('#m-e').value);
        if (!days.length || e <= s) return toast('pick days and a valid time range', true);
        const title = ovEl.querySelector('#m-name').value.trim() || 'activity';
        const color = ovEl.querySelector('.swatch.sel')?.dataset.c || '#5F6B5A';
        for (const d of days)
          await Api.post('/activities', { title, color, weekday: d, start_min: s, end_min: e });
        await loadAll();
        toast(`blocked \\u00b7 ${title} \\u00d7${days.length}`);
      });
    wireSwatches(ov);
    for (const b of ov.querySelectorAll('.daypick button'))
      b.onclick = () => b.classList.toggle('sel');
  }""",
  """  function activityModal(existing) {
    const initDays = new Set(existing?.days || []);
    const { ov } = modal(`
      <h2>${existing ? 'edit activity' : 'new activity'}</h2>
      <div class="frow"><label>title</label><input id="m-name" value="${esc(existing?.title || '')}" placeholder="CMPEN 331 lecture / lunch / workout" /></div>
      <div class="frow"><label>days</label>
        <div class="daypick">${DAYS.map((d, i) => `<button data-d="${i}" class="${initDays.has(i) ? 'sel' : ''}">${d}</button>`).join('')}</div></div>
      <div class="frow">
        <div><label>start</label><input id="m-s" type="time" value="${existing ? minToHM(existing.start_min) : nowHM()}" /></div>
        <div><label>end</label><input id="m-e" type="time" value="${existing ? minToHM(existing.end_min) : plusHM(50)}" /></div>
      </div>
      <div class="frow"><label>color</label>${swatchHtml(existing?.color || '#5F6B5A')}</div>
      ${existing ? '<div class="actions left"><button class="ghost danger-btn" data-m="del">delete</button></div>' : ''}
      ${ACTIONS(existing ? 'save' : 'block it')}`,
      async (act, ovEl) => {
        if (act === 'del') {
          await Promise.all((existing.ids).map((id) => Api.del('/activities/' + id)));
          await loadAll(); return toast('activity deleted');
        }
        if (act !== 'save') return;
        const days = [...ovEl.querySelectorAll('.daypick button.sel')].map((b) => +b.dataset.d);
        const s = hmToMin(ovEl.querySelector('#m-s').value);
        const e = hmToMin(ovEl.querySelector('#m-e').value);
        if (!days.length || e <= s) return toast('pick days and a valid time range', true);
        const title = ovEl.querySelector('#m-name').value.trim() || 'activity';
        const color = ovEl.querySelector('.swatch.sel')?.dataset.c || '#5F6B5A';
        if (existing) await Promise.all(existing.ids.map((id) => Api.del('/activities/' + id)));
        for (const d of days)
          await Api.post('/activities', { title, color, weekday: d, start_min: s, end_min: e });
        await loadAll();
        toast(`${existing ? 'updated' : 'blocked'} \\u00b7 ${title}`);
      });
    wireSwatches(ov);
    for (const b of ov.querySelectorAll('.daypick button'))
      b.onclick = () => b.classList.toggle('sel');
  }""")

p.write_text(js)
print("  FIX B click-to-edit: ok")
PY

# small CSS for clickable rows + danger button + left action row
grep -q ".side-item.clickable" webui/css/app.css || cat >> webui/css/app.css <<'CSS'

/* click-to-edit affordance + modal danger / left actions */
.side-item.clickable { cursor:pointer; border-radius:8px; }
.side-item.clickable:hover { background:var(--elev); }
.actions.left { justify-content:flex-start; }
.danger-btn { color:var(--red); border-color:var(--red); }
.danger-btn:hover { background:rgba(154,64,64,.14); color:var(--red); }
CSS
echo "  FIX B css: ok"

# ── FIX C: timezone — run the API container in your zone ────────────────────
python3 - "$TZNAME" <<'PY'
import sys, pathlib
tz = sys.argv[1]
p = pathlib.Path("docker-compose.yml")
yml = p.read_text()
if "TZ:" not in yml:
    yml = yml.replace(
      "      HIVE_DATABASE_URL: postgresql+psycopg://${HIVE_DB_USER}:${HIVE_DB_PASSWORD}@hive-db:5432/hive",
      "      HIVE_DATABASE_URL: postgresql+psycopg://${HIVE_DB_USER}:${HIVE_DB_PASSWORD}@hive-db:5432/hive\n      TZ: " + tz)
    p.write_text(yml)
    print(f"  FIX C timezone: container TZ set to {tz}")
else:
    # update existing TZ
    import re
    yml = re.sub(r"TZ: .*", f"TZ: {tz}", yml)
    p.write_text(yml)
    print(f"  FIX C timezone: updated to {tz}")
PY

# ensure tzdata is in the image so TZ takes effect
grep -q "tzdata" Dockerfile || python3 - <<'PY'
import pathlib
p = pathlib.Path("Dockerfile")
d = p.read_text()
d = d.replace(
  "COPY requirements.txt .",
  "RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*\nCOPY requirements.txt .")
p.write_text(d)
print("  FIX C: tzdata added to image")
PY

echo ""
echo "done. rebuild:  docker compose build --no-cache hive-api && docker compose up -d"
echo "your timezone is set to: $TZNAME  (re-run with a different IANA name to change)"
