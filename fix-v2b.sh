#!/usr/bin/env bash
# fix-v2b.sh — group repeated activities into one sidebar row; nicer empties.
# Run from inside hive-tasks/:  bash fix-v2b.sh
set -euo pipefail
[ -f webui/js/app.js ] || { echo "run me from inside hive-tasks/"; exit 1; }

python3 - <<'PY'
import pathlib
p = pathlib.Path("webui/js/app.js")
js = p.read_text()

# ---- group activities by title+time+color; show all weekdays on one row ----
old = """    $('activity-list').innerHTML = S.activities
      .slice().sort((a, b) => a.weekday - b.weekday || a.start_min - b.start_min)
      .map((a) => `
      <div class="side-item">
        <span class="dot" style="background:${a.color}"></span>
        <span class="nm">${esc(a.title)}</span>
        <span class="meta">${DAYS[a.weekday]} ${minToHM(a.start_min)}</span>
        <button class="x" data-del-act="${a.id}">✕</button>
      </div>`).join('') || '<p class="muted small">add lectures, lunch, sleep-ins…</p>';"""

new = """    const actGroups = {};
    for (const a of S.activities) {
      const k = `${a.title}|${a.start_min}|${a.end_min}|${a.color}`;
      (actGroups[k] ??= { ...a, ids: [], days: [] });
      actGroups[k].ids.push(a.id);
      actGroups[k].days.push(a.weekday);
    }
    const ABBR = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
    const dayAbbr = (ds) => ds.slice().sort((x, y) => x - y).map((d) => ABBR[d]).join('');
    $('activity-list').innerHTML = Object.values(actGroups)
      .sort((a, b) => Math.min(...a.days) - Math.min(...b.days) || a.start_min - b.start_min)
      .map((g) => `
      <div class="side-item">
        <span class="dot" style="background:${g.color}"></span>
        <span class="nm">${esc(g.title)}</span>
        <span class="meta">${dayAbbr(g.days)} ${minToHM(g.start_min)}</span>
        <button class="x" data-del-act="${g.ids.join(',')}">✕</button>
      </div>`).join('') || '<p class="muted small">no activities yet</p>';"""
assert old in js, "activity render block not found (already patched?)"
js = js.replace(old, new)

# ---- delete every weekday row of a grouped activity ----
old_del = """    for (const b of document.querySelectorAll('[data-del-act]'))
      b.onclick = async () => { await Api.del('/activities/' + b.dataset.delAct); loadAll(); };"""
new_del = """    for (const b of document.querySelectorAll('[data-del-act]'))
      b.onclick = async () => {
        const ids = b.dataset.delAct.split(',');
        await Promise.all(ids.map((id) => Api.del('/activities/' + id)));
        loadAll();
      };"""
assert old_del in js, "activity delete handler not found"
js = js.replace(old_del, new_del)

p.write_text(js)
print("activities grouped + placeholder fixed")
PY

echo "done. rebuild: docker compose build --no-cache hive-api && docker compose up -d"
