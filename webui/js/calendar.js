/* calendar.js — the week. awake shading, activities, planned blocks,
   due flags, now line, drag-to-plan, move/resize.
   Hand-rolled, no third-party calendar library — CSS-grid time axis +
   absolutely-positioned event blocks, native pointer/DnD interaction. */
const Cal = (() => {
  const HOUR = 46;                       // px per hour — matches --hourH
  const PAD = 10;                        // top inset — matches --calPadTop
  const DRAG_THRESHOLD = 4;              // px of pointer movement before a click counts as a drag
  let root, S, H;                        // root el, state, handlers
  let colRects = [];                     // for pointer drag targeting

  const pad = (n) => String(n).padStart(2, '0');
  const minToHM = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const fmtDur = (m) => m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? pad(m % 60) : ''}` : `${m}m`;
  const y = (min) => (min / 60) * HOUR + PAD;   // top position (with inset)
  const hPx = (durMin) => (durMin / 60) * HOUR;  // height for a duration (no inset)
  const snap = (min, step = 15) => Math.round(min / step) * step;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function tz() {
    const st = (S && S.settings) || {};
    return { home: st.home_tz || 'America/New_York', school: st.school_tz || 'America/New_York' };
  }
  function asUtc(iso) { return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z'); }
  function zoneMin(iso, zoneName) {
    // minutes-of-day for a UTC instant as seen in zoneName
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: zoneName, hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(asUtc(iso));
    const h = +parts.find((p) => p.type === 'hour').value % 24;
    const m = +parts.find((p) => p.type === 'minute').value;
    return h * 60 + m;
  }
  function zoneDay(iso, zoneName) {
    const p = new Intl.DateTimeFormat('en-US', {
      timeZone: zoneName, year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(asUtc(iso));
    const [mm, dd, yy] = p.split('/');
    return `${yy}-${mm}-${dd}`;
  }

  function mount(el, state, handlers) { root = el; S = state; H = handlers; }

  function courseOf(task) { return S.courses.find((c) => c.id === task?.course_id); }
  function taskOf(id) { return S.tasks.find((t) => t.id === id); }

  // ---------- render ----------
  let VIEW = 'week', VIEWN = 7;
  function setView(v, n) { VIEW = v; if (n) VIEWN = n; }

  function render() {
    closeDayPopover();
    if (VIEW === 'month') return renderMonth();
    return renderWeek();
  }

  function renderMonth() {
    const first = S.weekDays[0];
    const monthStart = new Date(first.getFullYear(), first.getMonth(), 1);
    const ws = (S.settings && S.settings.week_start != null) ? S.settings.week_start : 6;
    const lead = (monthStart.getDay() - ((ws + 1) % 7) + 7) % 7;
    const gridStart = new Date(monthStart); gridStart.setDate(1 - lead);
    const dows = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const order = [...Array(7)].map((_, i) => dows[(i + ws) % 7]);
    let html = '<div class="month-head">' + order.map((d) => `<div>${d}</div>`).join('') + '</div>';
    html += '<div class="month-grid mgrid-in">';
    for (let i = 0; i < 42; i++) {
      const d = new Date(gridStart); d.setDate(gridStart.getDate() + i);
      const iso = isoOf(d);
      const wd = (d.getDay() + 6) % 7;
      const dim = d.getMonth() !== first.getMonth() ? 'dim' : '';
      const today = iso === S.todayIso ? 'today' : '';
      const items = dayItems(iso, wd);
      const shown = items.slice(0, 3);
      html += `<div class="month-cell ${dim} ${today}" data-iso="${iso}" data-wd="${wd}">
        <div class="dom"><span>${d.getDate()}</span></div>
        <div class="mev-list">${shown.map(pillHtml).join('')}</div>
        ${items.length > 3 ? `<div class="mev-more" data-iso="${iso}">+${items.length - 3} more</div>` : ''}
      </div>`;
    }
    html += '</div>';
    root.innerHTML = html;
    wireMonth();
  }

  function dayInSchool(iso) {
    const z = (S.settings && S.settings.school_tz) || 'America/New_York';
    return zoneDay(iso, z);
  }

  // ---------- month view: real content (activities/planned/due), not just due-flags ----------
  function dayItems(iso, wd) {
    const items = [];
    for (const a of S.activities.filter((x) => x.weekday === wd)) {
      items.push({ kind: 'activity', id: a.id, title: a.title, color: a.color, notes: a.notes,
        start_min: a.start_min, sub: `${minToHM(a.start_min)}–${minToHM(a.end_min)}` });
    }
    for (const p of S.planned.filter((x) => zoneDay(x.start_at, tz().home) === iso)) {
      const t = taskOf(p.task_id) || {};
      const c = courseOf(t);
      const sMin = zoneMin(p.start_at, tz().home);
      const eMin = zoneMin(p.end_at, tz().home) || 1440;
      items.push({ kind: 'planned', id: p.id, title: t.title || '?', color: c?.color || '#5B5FEF', notes: t.notes,
        start_min: sMin, sub: `${minToHM(sMin)}–${minToHM(eMin)}` });
    }
    for (const t of S.tasks.filter((x) => x.status !== 'done' && x.due_at && dayInSchool(x.due_at) === iso)) {
      const c = courseOf(t);
      const m = zoneMin(t.due_at, tz().school);
      items.push({ kind: 'due', id: t.id, title: t.title, color: c?.color || '#8E8E93', notes: t.notes,
        start_min: m, sub: `due ${minToHM(m)}` });
    }
    return items.sort((x, y) => x.start_min - y.start_min);
  }

  function pillHtml(it) {
    return `<div class="mev mev-${it.kind}" data-kind="${it.kind}" data-id="${it.id}"
      style="background:${hexA(it.color, 0.16)};border-color:${hexA(it.color, 0.4)}">
      <span class="dot" style="background:${it.color}"></span><span class="tt">${esc(it.title)}</span></div>`;
  }

  function openItem(kind, id) {
    if (kind === 'activity') H.onActivityMenu(id);
    else if (kind === 'planned') { const b = S.planned.find((p) => p.id === id); if (b) H.onBlockMenu(b); }
    else if (kind === 'due') H.onTaskMenu(id);
  }

  function wireMonth() {
    const grid = root.querySelector('.month-grid');
    if (!grid) return;
    grid.addEventListener('click', (e) => {
      const pill = e.target.closest('.mev');
      if (pill) { openItem(pill.dataset.kind, +pill.dataset.id); return; }
      const cell = e.target.closest('.month-cell');
      if (cell) openDayPopover(cell);
    });
  }

  // ---------- month view: day popover (agenda + quick add) ----------
  let dayPop = null;
  function closeDayPopover() {
    if (dayPop) { dayPop.remove(); dayPop = null; }
    document.removeEventListener('pointerdown', onDayPopOutside, true);
    document.removeEventListener('keydown', onDayPopKey, true);
  }
  function onDayPopOutside(e) { if (dayPop && !dayPop.contains(e.target)) closeDayPopover(); }
  function onDayPopKey(e) { if (e.key === 'Escape') closeDayPopover(); }

  function openDayPopover(cellEl) {
    closeDayPopover();
    const iso = cellEl.dataset.iso, wd = +cellEl.dataset.wd;
    const items = dayItems(iso, wd);
    const heading = new Date(iso + 'T00:00').toLocaleDateString(undefined,
      { weekday: 'long', month: 'long', day: 'numeric' });
    const pop = document.createElement('div');
    pop.className = 'day-pop';
    pop.innerHTML = `
      <div class="day-pop-head">${heading}</div>
      <div class="day-pop-list">${items.length ? items.map((it) => `
        <div class="day-pop-row" data-kind="${it.kind}" data-id="${it.id}">
          <span class="dot" style="background:${it.color}"></span>
          <span class="dp-txt"><b>${esc(it.title)}</b><span class="dp-sub">${esc(it.sub)}</span></span>
        </div>`).join('') : '<p class="muted small">nothing scheduled</p>'}</div>
      <div class="day-pop-actions">
        <button type="button" class="ghost" data-add="task">+ add task</button>
        <button type="button" class="ghost" data-add="activity">+ add activity</button>
      </div>`;
    document.body.appendChild(pop);
    dayPop = pop;

    pop.querySelectorAll('.day-pop-row').forEach((row) => {
      row.onclick = () => { closeDayPopover(); openItem(row.dataset.kind, +row.dataset.id); };
    });
    pop.querySelector('[data-add="task"]').onclick = () => { closeDayPopover(); H.onNewTask(iso); };
    pop.querySelector('[data-add="activity"]').onclick = () => { closeDayPopover(); H.onNewActivity(wd); };

    // anchor under the clicked cell; flip left/up rather than overflow the viewport
    const r = cellEl.getBoundingClientRect();
    const pr = pop.getBoundingClientRect();
    let top = r.bottom + 6, left = r.left;
    if (left + pr.width > window.innerWidth - 8) left = window.innerWidth - pr.width - 8;
    if (top + pr.height > window.innerHeight - 8) top = r.top - pr.height - 6;
    top = Math.max(8, top); left = Math.max(8, left);
    pop.style.top = top + 'px';
    pop.style.left = left + 'px';

    document.addEventListener('pointerdown', onDayPopOutside, true);
    document.addEventListener('keydown', onDayPopKey, true);
  }

  function renderWeek() {
    const days = S.weekDays;                       // [Date x7]
    const todayIso = S.todayIso;
    const avail = Object.fromEntries((S.availability || []).map((a) => [a.date, a]));

    let html = '<div class="cal-grid">';
    html += '<div class="cal-corner"></div>';
    for (const d of days) {
      const iso = isoOf(d);
      const a = avail[iso] || {};
      html += `<div class="cal-head ${iso === todayIso ? 'today' : ''}">
        <div class="dow">${d.toLocaleDateString(undefined, { weekday: 'short' }).toLowerCase()}</div>
        <div class="dom"><span>${d.getDate()}</span></div>
        <div class="freelab">${a.in_term === false ? 'break' : fmtDur(a.free_min || 0)}</div>
        ${a.due_count ? `<div class="duebanner">${a.due_count} due</div>` : ''}
      </div>`;
    }

    // gutter
    html += '<div class="gutter-cell" style="position:sticky;">';
    for (let h = 0; h < 24; h++) html += `<div class="hour-label" style="top:${y(h * 60)}px">${pad(h)}:00</div>`;
    html += '</div>';

    // day columns
    for (const d of days) {
      const iso = isoOf(d);
      const a = avail[iso] || { awake: [480, 1410] };
      const past = iso < todayIso;
      html += `<div class="day-col ${past ? 'past' : ''}" data-date="${iso}"
                    style="height:${24 * HOUR + PAD * 2}px">`;
      for (let h = 1; h < 24; h++) html += `<div class="hour-line" style="top:${y(h * 60)}px"></div>`;
      const [as, ae] = a.awake || [480, 1410];
      html += `<div class="sleep" style="top:0;height:${hPx(as)}px"></div>`;
      html += `<div class="sleep" style="top:${y(ae)}px;height:${hPx(1440 - ae)}px"></div>`;

      // activities for this weekday
      const wd = (d.getDay() + 6) % 7;
      for (const act of S.activities.filter((x) => x.weekday === wd)) {
        html += evHtml({
          cls: 'activity', id: act.id, top: y(act.start_min), h: hPx(act.end_min - act.start_min),
          color: act.color, title: act.title, resize: true,
          sub: `${minToHM(act.start_min)}–${minToHM(act.end_min)}`,
        });
      }

      // planned blocks on this date
      for (const p of S.planned.filter((x) => zoneDay(x.start_at, tz().home) === iso)) {
        const t = taskOf(p.task_id) || {};
        const c = courseOf(t);
        const sMin = zoneMin(p.start_at, tz().home);
        const eMin = zoneMin(p.end_at, tz().home) || 1440;
        const nowM = new Date().getHours() * 60 + new Date().getMinutes();
        const isPassed = (iso < todayIso) || (iso === todayIso && eMin <= nowM);
        html += evHtml({
          cls: 'planned' + (p.completed ? ' done' : '') + (isPassed ? ' passed' : ''), id: p.id,
          top: y(sMin), h: hPx(eMin - sMin), color: c?.color || '#5B5FEF',
          title: t.title || '?', sub: `${minToHM(sMin)}–${minToHM(eMin)}`,
          resize: !p.completed,
        });
      }

      // due flags
      for (const t of S.tasks.filter((x) => x.status !== 'done'
          && x.due_at && zoneDay(x.due_at, tz().school) === iso)) {
        const m = zoneMin(t.due_at, tz().school);
        const lv = (S.cushionByTask[t.id] || {}).level;
        html += `<div class="due-flag ${lv === 'red' ? 'red' : ''}"
                      style="top:${y(m) - 7}px">⚑ ${esc(t.title)}</div>`;
      }

      // now line + today's passed-time tint (behind blocks)
      if (iso === todayIso) {
        const nm = new Date();
        const nowMin = nm.getHours() * 60 + nm.getMinutes();
        html += `<div class="passed-tint" style="top:0;height:${hPx(nowMin)}px"></div>`;
        html += `<div class="now-line" data-now style="top:${y(nowMin)}px"></div>`;
      }
      html += '</div>';
    }
    html += '</div>';
    root.innerHTML = html;

    cacheCols();
    wireDnD();
    wirePointer();
    if (!render._scrolled) {
      root.scrollTop = y(S.settings?.day_start_min ?? 480) - 8;
      render._scrolled = true;
    }
  }

  function evHtml({ cls, id, top, h, color, title, sub, resize }) {
    return `<div class="ev ${cls}" ${id ? `data-pid="${id}"` : ''}
      style="top:${top}px;height:${Math.max(h, 16)}px;
             background:${hexA(color, 0.16)};border-color:${hexA(color, 0.4)}">
      ${resize ? '<div class="rs rs-top" data-edge="s"></div>' : ''}
      <div class="t" style="color:${color}">${esc(title)}</div>
      <div class="d">${sub}</div>
      ${resize ? '<div class="rs rs-bot" data-edge="e"></div>' : ''}</div>`;
  }

  function hexA(hex, a) {
    const h = (hex || '#5B5FEF').replace('#', '');
    const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  function hmToMin(hm) { const [h, m] = hm.split(':').map(Number); return h * 60 + m; }
  function isoOf(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function cacheCols() {
    colRects = [...root.querySelectorAll('.day-col')].map((el) => ({ el, date: el.dataset.date }));
  }
  function colAt(clientX) {
    for (const c of colRects) {
      const r = c.el.getBoundingClientRect();
      if (clientX >= r.left && clientX < r.right) return c;
    }
    return null;
  }
  function minAt(col, clientY) {
    const r = col.el.getBoundingClientRect();
    return Math.max(0, Math.min(1440, ((clientY - r.top - PAD) / HOUR) * 60));
  }

  // ---------- drag-to-plan (native HTML5 DnD from panel cards) ----------
  const WD_ABBR = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const weekdayOf = (dateIso) => (new Date(dateIso + 'T00:00').getDay() + 6) % 7;
  let ghost = null;
  function wireDnD() {
    for (const { el } of colRects) {
      el.addEventListener('dragover', (e) => {
        const tid = +(window._dragTaskId || 0);
        const act = window._dragActivity || null;
        if (!tid && !act) return;
        e.preventDefault();
        el.classList.add('droptarget');
        const start = snap(minAt({ el }, e.clientY), 30);
        const dur = act ? act.durationMin : planDuration(tid);
        if (!ghost) { ghost = document.createElement('div'); ghost.className = 'drop-ghost'; }
        if (ghost.parentNode !== el) el.appendChild(ghost);
        ghost.style.top = y(start) + 'px';
        ghost.style.height = hPx(dur) + 'px';
        // dropping an activity retimes/places just THIS one day's occurrence
        // (like planning a task), not the whole recurring group.
        ghost.textContent = act ? `${act.title} · ${WD_ABBR[weekdayOf(el.dataset.date)]} · ${minToHM(start)}–${minToHM(start + dur)}`
                                 : `${minToHM(start)} · ${fmtDur(dur)}`;
        ghost.dataset.start = start;
      });
      el.addEventListener('dragleave', () => el.classList.remove('droptarget'));
      el.addEventListener('drop', (e) => {
        e.preventDefault();
        el.classList.remove('droptarget');
        const act = window._dragActivity || null;
        const tid = +(e.dataTransfer.getData('text/task') || window._dragTaskId || 0);
        const start = +(ghost?.dataset.start ?? snap(minAt({ el }, e.clientY), 30));
        if (ghost) { ghost.remove(); ghost = null; }
        if (act) H.onMoveActivity(act, start, start + act.durationMin, weekdayOf(el.dataset.date));
        else if (tid) H.onPlan(tid, el.dataset.date, start, planDuration(tid));
      });
    }
    const cleanup = () => {
      if (ghost) { ghost.remove(); ghost = null; }
      for (const { el } of colRects) el.classList.remove('droptarget');
    };
    root.addEventListener('dragend', cleanup);
    document.addEventListener('dragend', cleanup);
    document.addEventListener('drop', cleanup);
  }
  function planDuration(taskId) {
    const t = taskOf(taskId);
    const rem = t ? Math.max(0, t.time_needed_min - t.time_spent_min) : 60;
    return Math.max(30, Math.min(rem || 60, 120));
  }

  // ---------- pointer move / resize of planned blocks ----------
  function wirePointer() {
    for (const ev of root.querySelectorAll('.ev.planned')) {
      ev.addEventListener('pointerdown', (e) => {
        const pid = +ev.dataset.pid;
        const block = S.planned.find((p) => p.id === pid);
        startDrag(e, ev, block);
      });
    }
    for (const ev of root.querySelectorAll('.ev.activity')) {
      ev.addEventListener('pointerdown', (e) => {
        const aid = +ev.dataset.pid;
        const act = S.activities.find((a) => a.id === aid);
        startActivityDrag(e, ev, act);
      });
    }
  }

  // Same click-vs-drag-vs-resize distinction as startDrag, but for a single
  // concrete activity occurrence: a plain click opens its edit menu, dragging
  // the body moves it (which day + what time), dragging a handle resizes it
  // — same as a planned task block.
  function startActivityDrag(e, el, act) {
    if (!act) return;
    e.preventDefault();
    const edge = e.target.classList.contains('rs') ? e.target.dataset.edge : null;
    const durationMin = act.end_min - act.start_min;
    const grabOffset = minAt(colAt(e.clientX) || colRects[0], e.clientY) - act.start_min;
    let moved = false;
    let curCol = colAt(e.clientX) || colRects[0];
    let cur = { s: act.start_min, e: act.end_min };
    const downX = e.clientX, downY = e.clientY;

    const onMove = (me) => {
      // Ignore sub-pixel jitter so a plain click (which can still fire a
      // pointermove or two) doesn't get misread as a drag.
      if (!moved && Math.hypot(me.clientX - downX, me.clientY - downY) < DRAG_THRESHOLD) return;
      const col = colAt(me.clientX);
      if (!col) return;
      moved = true;
      el.classList.add('dragging');
      if (edge === 'e') {
        // resize bottom: move end only, keep start
        cur.e = Math.min(1440, Math.max(cur.s + 15, snap(minAt(col, me.clientY), 15)));
      } else if (edge === 's') {
        // resize top: move start only, keep end
        cur.s = Math.max(0, Math.min(cur.e - 15, snap(minAt(col, me.clientY), 15)));
      } else {
        // move: shift whole block, preserve duration, allow column change
        curCol = col;
        let ns = snap(minAt(col, me.clientY) - grabOffset, 15);
        ns = Math.max(0, Math.min(ns, 1440 - durationMin));
        cur = { s: ns, e: ns + durationMin };
        if (col.el !== el.parentNode) col.el.appendChild(el);
      }
      el.style.top = y(cur.s) + 'px';
      el.style.height = hPx(cur.e - cur.s) + 'px';
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      el.classList.remove('dragging');
      if (moved) {
        H.onMoveActivity({
          ids: [act.id], title: act.title, color: act.color,
          days: [act.weekday], course_id: act.course_id ?? null,
        }, cur.s, cur.e, weekdayOf(curCol.date));
      } else {
        H.onActivityMenu(act.id);
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }

  function startDrag(e, el, block) {
    if (!block) return;
    e.preventDefault();
    // resize edge from the handle that was grabbed (data-edge="s"|"e"); else move
    const edge = e.target.classList.contains('rs') ? e.target.dataset.edge : null;
    const startMin0 = zoneMin(block.start_at, tz().home);
    const endMin0 = zoneMin(block.end_at, tz().home) || 1440;
    const grabOffset = minAt(colAt(e.clientX) || colRects[0], e.clientY) - startMin0;
    let moved = false, cur = { date: zoneDay(block.start_at, tz().home), s: startMin0, e: endMin0 };
    const downX = e.clientX, downY = e.clientY;

    const onMove = (me) => {
      if (!moved && Math.hypot(me.clientX - downX, me.clientY - downY) < DRAG_THRESHOLD) return;
      const col = colAt(me.clientX);
      if (!col) return;
      moved = true;
      el.classList.add('dragging');
      if (edge === 'e') {
        // resize bottom: move end only, keep start
        cur.e = Math.min(1440, Math.max(cur.s + 15, snap(minAt(col, me.clientY), 15)));
      } else if (edge === 's') {
        // resize top: move start only, keep end
        cur.s = Math.max(0, Math.min(cur.e - 15, snap(minAt(col, me.clientY), 15)));
      } else {
        // move: shift whole block, preserve duration, allow column change
        const dur = endMin0 - startMin0;
        let ns = snap(minAt(col, me.clientY) - grabOffset, 15);
        ns = Math.max(0, Math.min(ns, 1440 - dur));
        cur = { date: col.date, s: ns, e: ns + dur };
        if (col.el !== el.parentNode) col.el.appendChild(el);
      }
      el.style.top = y(cur.s) + 'px';
      el.style.height = hPx(cur.e - cur.s) + 'px';
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      el.classList.remove('dragging');
      if (moved) H.onMovePlanned(block.id, cur.date, cur.s, cur.e);
      else H.onBlockMenu(block);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }

  // keep the now-line honest
  setInterval(() => {
    const line = root?.querySelector('[data-now]');
    if (line) {
      const n = new Date();
      line.style.top = y(n.getHours() * 60 + n.getMinutes()) + 'px';
    }
  }, 60000);

  function resize() { cacheCols(); }

  return { mount, render, setView, resize };
})();
