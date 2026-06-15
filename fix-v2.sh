#!/usr/bin/env bash
# fix-v2.sh — apply all six fixes in place. Run from the hive-tasks/ dir:
#   bash fix-v2.sh
# Idempotent-ish: it rewrites whole blocks, so re-running is safe.
set -euo pipefail

[ -f webui/css/app.css ] || { echo "run me from inside hive-tasks/"; exit 1; }
echo "patching scholar. v2…"

# ── FIX 1: calendar grid rows (the empty-calendar bug) ─────────────────────
# The grid needs an explicit 2-row template: sticky header row (auto) + body
# row (the 24h column height). We also force header cells into row 1 and the
# gutter + day columns into row 2 so they actually fill the space.
python3 - <<'PY'
import re, pathlib
p = pathlib.Path("webui/css/app.css")
css = p.read_text()

old = """.cal-grid { display:grid; grid-template-columns:var(--gutter) repeat(7,1fr);
  min-width:760px; }"""
new = """.cal-grid { display:grid; grid-template-columns:var(--gutter) repeat(7,1fr);
  grid-template-rows:auto calc(24 * var(--hourH)); min-width:760px; }
.cal-grid > .cal-head { grid-row:1; }
.cal-grid > .gutter-cell, .cal-grid > .day-col { grid-row:2; }"""
assert old in css, "FIX1: calendar grid block not found (already patched?)"
css = css.replace(old, new)

# gutter must be the full body height too, and day cols stretch to the row
css = css.replace(
  ".gutter-cell { position:sticky; left:0; background:var(--bg); z-index:4; }",
  ".gutter-cell { position:sticky; left:0; background:var(--bg); z-index:4;\n  height:calc(24 * var(--hourH)); }")

p.write_text(css)
print("  FIX1 calendar grid: ok")
PY

# ── FIX 5 (CSS support for live swatch ring) ───────────────────────────────
grep -q ".swatch.sel { box-shadow" webui/css/app.css || cat >> webui/css/app.css <<'CSS'

/* clearer selected swatch + live ring (fix 5) */
.swatch { width:30px; height:30px; border-radius:50%; cursor:pointer;
  border:2px solid transparent; box-sizing:border-box; transition:transform .12s ease; }
.swatch:hover { transform:scale(1.08); }
.swatch.sel { box-shadow:0 0 0 2px var(--bg), 0 0 0 4px var(--accent); }
.swatches { display:flex; gap:10px; flex-wrap:wrap; }
/* modal cancel button row */
.modal .actions { display:flex; gap:8px; justify-content:flex-end; align-items:center; }
.modal .actions .spacer { flex:1; }
/* task-list view (fix 6) */
.tasklist { padding:14px 18px; overflow:auto; }
.tl-group { margin-bottom:18px; }
.tl-course { font-family:var(--serif); font-size:17px; margin-bottom:6px;
  display:flex; align-items:center; gap:8px; }
.tl-row { display:flex; align-items:center; gap:10px; padding:8px 10px;
  border:1px solid var(--line); border-radius:var(--r); margin-bottom:6px; }
.tl-row .grow { flex:1; min-width:0; }
.tl-row .cu { font-size:11px; padding:1px 8px; border-radius:var(--pill); }
.tl-row .cu.green { color:var(--green); border:1px solid var(--green); }
.tl-row .cu.yellow { color:var(--yellow); border:1px solid var(--yellow); }
.tl-row .cu.red { color:var(--red); border:1px solid var(--red); }
.tl-row .cu.none { color:var(--faint); border:1px solid var(--line); }
CSS
echo "  FIX5/6 css: ok"

# ── FIXES 2,3,4,5b,6 live in app.js ────────────────────────────────────────
python3 - <<'PY'
import pathlib
p = pathlib.Path("webui/js/app.js")
js = p.read_text()

# FIX 2 — give every modal a cancel button + Esc-to-close.
# Add a [data-m="cancel"] handler path and key listener inside modal().
old_modal = """  function modal(html, onAction) {
    const rootEl = $('modal-root');
    rootEl.innerHTML = `<div class="overlay"><div class="modal">${html}</div></div>`;
    const ov = rootEl.firstElementChild;
    ov.addEventListener('click', (e) => { if (e.target === ov) close(); });
    function close() { rootEl.innerHTML = ''; }
    for (const b of ov.querySelectorAll('[data-m]'))
      b.onclick = async () => { await onAction?.(b.dataset.m, ov); close(); };
    return { ov, close };
  }"""
new_modal = """  function modal(html, onAction) {
    const rootEl = $('modal-root');
    rootEl.innerHTML = `<div class="overlay"><div class="modal">${html}</div></div>`;
    const ov = rootEl.firstElementChild;
    ov.addEventListener('click', (e) => { if (e.target === ov) close(); });
    function close() { rootEl.innerHTML = ''; document.removeEventListener('keydown', onKey); }
    function onKey(e) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onKey);
    for (const b of ov.querySelectorAll('[data-m]'))
      b.onclick = async () => {
        if (b.dataset.m === 'cancel') return close();   // cancel never calls onAction
        try { await onAction?.(b.dataset.m, ov); } finally { close(); }
      };
    return { ov, close };
  }
  // every modal's button row should carry a cancel; helper to append one
  const ACTIONS = (saveLabel, saveAttr = 'save') =>
    `<div class="actions"><span class="spacer"></span>
       <button class="ghost" data-m="cancel">cancel</button>
       <button class="primary" data-m="${saveAttr}">${saveLabel}</button></div>`;
"""
assert old_modal in js, "modal() block not found"
js = js.replace(old_modal, new_modal)

# Swap each modal's hand-rolled actions row for ACTIONS(...) so all get cancel.
js = js.replace(
  '<div class="actions"><button class="primary" data-m="save">save</button></div>`,\n      async (act, ovEl) => {\n        if (act !== \'save\') return;\n        const dd',
  '${ACTIONS(\'save\')}`,\n      async (act, ovEl) => {\n        if (act !== \'save\') return;\n        const dd')
js = js.replace(
  '<div class="actions"><button class="primary" data-m="save">add</button></div>`,\n      async (act, ov) => {\n        if (act !== \'save\') return;\n        await Api.post(\'/courses\'',
  '${ACTIONS(\'add\')}`,\n      async (act, ov) => {\n        if (act !== \'save\') return;\n        await Api.post(\'/courses\'')
js = js.replace(
  '<div class="actions"><button class="primary" data-m="save">block it</button></div>`,',
  '${ACTIONS(\'block it\')}`,')
js = js.replace(
  '<div class="actions"><button class="primary" data-m="save">save</button></div>`,\n      async (act, ov) => {\n        if (act !== \'save\') return;\n        const body = { canvas_base_url',
  '${ACTIONS(\'save\')}`,\n      async (act, ov) => {\n        if (act !== \'save\') return;\n        const body = { canvas_base_url')
js = js.replace(
  '<div class="actions"><button class="primary" data-m="save">save</button></div>`,\n      async (act, ov) => {\n        if (act !== \'save\') return;\n        await Api.put(\'/config/settings\', {\n          min_block_min',
  '${ACTIONS(\'save\')}`,\n      async (act, ov) => {\n        if (act !== \'save\') return;\n        await Api.put(\'/config/settings\', {\n          min_block_min')

# FIX 3 — confirmation toasts after course & task saves.
js = js.replace(
  "        await Api.post('/courses', {\n          name: ov.querySelector('#m-name').value.trim() || 'course',\n          color: ov.querySelector('.swatch.sel')?.dataset.c || PALETTE[0],\n        });\n        await loadAll();",
  "        const nm = ov.querySelector('#m-name').value.trim() || 'course';\n        await Api.post('/courses', {\n          name: nm,\n          color: ov.querySelector('.swatch.sel')?.dataset.c || PALETTE[0],\n        });\n        await loadAll();\n        toast(`added course \\u00b7 ${nm}`);")
js = js.replace(
  "        t ? await Api.patch('/tasks/' + t.id, body) : await Api.post('/tasks', body);\n        await loadAll();",
  "        t ? await Api.patch('/tasks/' + t.id, body) : await Api.post('/tasks', body);\n        await loadAll();\n        toast(t ? `updated \\u00b7 ${body.title}` : `added task \\u00b7 ${body.title}`);")
js = js.replace(
  "        for (const d of days)\n          await Api.post('/activities', { title, color, weekday: d, start_min: s, end_min: e });\n        await loadAll();",
  "        for (const d of days)\n          await Api.post('/activities', { title, color, weekday: d, start_min: s, end_min: e });\n        await loadAll();\n        toast(`blocked \\u00b7 ${title} \\u00d7${days.length}`);")

# FIX 5b — show the chosen color as a live ring is CSS; also default course
# swatch should start visibly selected (already has .sel). Make activity color
# default selected too (swatchHtml('#5F6B5A') already passes sel). ok.

# FIX 4 — activity start/end default to the current hour, not 10:00.
js = js.replace(
  '<div><label>start</label><input id="m-s" type="time" value="10:00" /></div>\n        <div><label>end</label><input id="m-e" type="time" value="10:50" /></div>',
  '<div><label>start</label><input id="m-s" type="time" value="${nowHM()}" /></div>\n        <div><label>end</label><input id="m-e" type="time" value="${plusHM(50)}" /></div>')

# add nowHM/plusHM helpers near the top utils
js = js.replace(
  "  const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];",
  "  const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];\n  const nowHM = () => { const n = new Date(); return `${pad(n.getHours())}:${pad(n.getMinutes())}`; };\n  const plusHM = (mins) => { const n = new Date(Date.now() + mins * 60000); return `${pad(n.getHours())}:${pad(n.getMinutes())}`; };")

# FIX 6 — Task List tab actually works. Wire both tabs + a renderTaskList().
# Replace the dead tab markup wiring by adding tab handlers in wireChrome and
# a renderer. We hook into the existing topbar tabs.
js = js.replace(
  "    document.querySelector('[data-view=\"insights\"]').onclick =\n      () => toast('cushion charts, timeline & analytics land in phase 5');\n  }",
  "    document.querySelector('[data-view=\"insights\"]').onclick =\n      () => toast('cushion charts, timeline & analytics land in phase 5');\n    wireTabs();\n  }\n\n  // ---------- calendar / task-list tab switch (fix 6) ----------\n  function wireTabs() {\n    const tabs = document.querySelectorAll('.topbar .tab');\n    if (tabs.length < 2) return;\n    const [calTab, listTab] = tabs;\n    calTab.classList.remove('muted'); listTab.classList.remove('muted');\n    calTab.onclick = () => setView('calendar', calTab, listTab);\n    listTab.onclick = () => setView('list', listTab, calTab);\n  }\n  function setView(view, on, off) {\n    on.classList.add('active'); off.classList.remove('active');\n    const cal = $('calendar');\n    let list = $('tasklist');\n    if (view === 'list') {\n      cal.classList.add('hidden');\n      if (!list) { list = document.createElement('div'); list.id = 'tasklist';\n        list.className = 'tasklist'; cal.parentNode.appendChild(list); }\n      list.classList.remove('hidden');\n      renderTaskList(list);\n    } else {\n      cal.classList.remove('hidden');\n      if (list) list.classList.add('hidden');\n    }\n  }\n  function renderTaskList(el) {\n    const open = S.tasks.filter((t) => t.status !== 'done')\n      .sort((a, b) => (a.due_at || '9999').localeCompare(b.due_at || '9999'));\n    const byCourse = {};\n    for (const t of open) (byCourse[t.course_id ?? 'none'] ??= []).push(t);\n    const cname = Object.fromEntries(S.courses.map((c) => [c.id, c]));\n    el.innerHTML = open.length ? Object.entries(byCourse).map(([cid, ts]) => {\n      const c = cname[cid];\n      return `<div class=\"tl-group\">\n        <div class=\"tl-course\"><span class=\"dot\" style=\"background:${c?.color || '#8A7F73'}\"></span>${esc(c?.name || 'unassigned')}</div>\n        ${ts.map((t) => {\n          const cu = S.cushionByTask[t.id];\n          const lv = cu ? cu.level : 'none';\n          const cuTxt = cu ? `${cu.cushion_min < 0 ? '-' : ''}${Math.abs(Math.round(cu.cushion_min/60))}h cushion` : 'no due date';\n          return `<div class=\"tl-row\">\n            <span class=\"cu ${lv}\">${cuTxt}</span>\n            <div class=\"grow\"><div>${esc(t.title)}</div>\n              <div class=\"muted small\">${t.due_at ? 'due ' + t.due_at.slice(0,10) : 'unscheduled'} \\u00b7 ${t.time_spent_min}/${t.time_needed_min}m</div></div>\n            <button class=\"ghost small-btn\" data-tl-done=\"${t.id}\">done</button>\n            <button class=\"ghost small-btn\" data-tl-edit=\"${t.id}\">edit</button>\n          </div>`;\n        }).join('')}\n      </div>`;\n    }).join('') : '<p class=\"muted\">no open tasks. add one, or sync Canvas.</p>';\n    for (const b of el.querySelectorAll('[data-tl-done]'))\n      b.onclick = () => onTaskAction('done', +b.dataset.tlDone).then(() => renderTaskList(el));\n    for (const b of el.querySelectorAll('[data-tl-edit]'))\n      b.onclick = () => onTaskAction('edit', +b.dataset.tlEdit);\n  }")

# keep the task list fresh when data reloads while it's open
js = js.replace(
  "  function renderAll() {\n    renderSidebar(); renderTop(); Cal.render(); Panel.render();\n  }",
  "  function renderAll() {\n    renderSidebar(); renderTop(); Cal.render(); Panel.render();\n    const list = document.getElementById('tasklist');\n    if (list && !list.classList.contains('hidden')) renderTaskList(list);\n  }")

p.write_text(js)
print("  FIX2/3/4/6 app.js: ok")
PY

echo "patched. now: docker compose up -d --build hive-api  (then hard-refresh browser)"
