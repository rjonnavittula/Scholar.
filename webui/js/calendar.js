/* calendar.js — the week. awake shading, activities, planned blocks,
   due flags, now line, drag-to-plan, move/resize. */
const Cal = (() => {
  const HOUR = 46;                       // px per hour — matches --hourH
  const PAD = 10;                        // top inset — matches --calPadTop
  let root, S, H;                        // root el, state, handlers
  let colRects = [];                     // for pointer drag targeting

  const pad = (n) => String(n).padStart(2, '0');
  const minToHM = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const fmtDur = (m) => m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? pad(m % 60) : ''}` : `${m}m`;
  const y = (min) => (min / 60) * HOUR + PAD;   // uniform top inset for all placement
  const snap = (min, step = 15) => Math.round(min / step) * step;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function tz() {
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

  function mount(el, state, handlers) { root = el; S = state; H = handlers; }

  function courseOf(task) { return S.courses.find((c) => c.id === task?.course_id); }
  function taskOf(id) { return S.tasks.find((t) => t.id === id); }

  // ---------- render ----------
  let VIEW = 'week', VIEWN = 7;
  function setView(v, n) { VIEW = v; if (n) VIEWN = n; }

  function render() {
    if (VIEW === 'month') return renderMonth();
    // 'day' and 'nextN' reuse the time-grid; app.js sets S.weekDays length.
    return renderWeek();
  }

  function renderMonth() {
    const first = S.weekDays[0];
    const monthStart = new Date(first.getFullYear(), first.getMonth(), 1);
    const ws = (S.settings && S.settings.week_start != null) ? S.settings.week_start : 6;
    const lead = (monthStart.getDay() - ((ws + 1) % 7) + 7) % 7;
    const gridStart = new Date(monthStart); gridStart.setDate(1 - lead);
    const dows = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const order = [...Array(7)].map((_, i) => dows[(i + ws) % 7]);
    let html = '<div class="month-head">' + order.map((d) => `<div>${d}</div>`).join('') + '</div>';
    html += '<div class="month-grid">';
    for (let i = 0; i < 42; i++) {
      const d = new Date(gridStart); d.setDate(gridStart.getDate() + i);
      const iso = isoOf(d);
      const dim = d.getMonth() !== first.getMonth() ? 'dim' : '';
      const today = iso === S.todayIso ? 'today' : '';
      const due = S.tasks.filter((t) => t.status !== 'done' && t.due_at &&
        dayInSchool(t.due_at) === iso);
      html += `<div class="month-cell ${dim} ${today}"><div class="dom">${d.getDate()}</div>` +
        due.slice(0, 3).map((t) => `<div class="mev"><span class="due">\u29BF</span> ${esc(t.title)}</div>`).join('') +
        (due.length > 3 ? `<div class="mev">+${due.length - 3} more</div>` : '') + '</div>';
    }
    html += '</div>';
    root.innerHTML = html;
  }

  function dayInSchool(iso) {
    const z = (S.settings && S.settings.school_tz) || 'America/New_York';
    return zoneDay(iso, z);
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
        <div class="dom">${d.getDate()}</div>
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
      html += `<div class="sleep" style="top:0;height:${y(as)}px"></div>`;
      html += `<div class="sleep" style="top:${y(ae)}px;height:${y(1440 - ae)}px"></div>`;
      html += `<div class="awake-tint" style="top:${y(as)}px;height:${y(ae - as)}px"></div>`;

      // activities for this weekday
      const wd = (d.getDay() + 6) % 7;
      for (const act of S.activities.filter((x) => x.weekday === wd)) {
        html += evHtml({
          cls: 'activity', top: y(act.start_min), h: y(act.end_min - act.start_min),
          color: act.color, title: act.title,
          sub: `${minToHM(act.start_min)}–${minToHM(act.end_min)}`,
        });
      }

      // planned blocks on this date
      for (const p of S.planned.filter((x) => zoneDay(x.start_at, tz().home) === iso)) {
        const t = taskOf(p.task_id) || {};
        const c = courseOf(t);
        const sMin = zoneMin(p.start_at, tz().home);
        const eMin = zoneMin(p.end_at, tz().home) || 1440;
        html += evHtml({
          cls: 'planned' + (p.completed ? ' done' : ''), id: p.id,
          top: y(sMin), h: y(eMin - sMin), color: c?.color || '#8A7F73',
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

      // now line
      if (iso === todayIso) {
        const nm = new Date();
        html += `<div class="now-line" data-now style="top:${y(nm.getHours() * 60 + nm.getMinutes())}px"></div>`;
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
             background:${hexA(color, 0.16)};border-color:${hexA(color, 0.55)}">
      <div class="t" style="color:${color}">${esc(title)}</div>
      <div class="d">${sub}</div>${resize ? '<div class="rs"></div>' : ''}</div>`;
  }

  function hexA(hex, a) {
    const n = parseInt(hex.replace('#', ''), 16);
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
    return Math.max(0, Math.min(1440, ((clientY - r.top) / HOUR) * 60));
  }

  // ---------- drag-to-plan (HTML5 DnD from panel cards) ----------
  let ghost = null;
  function wireDnD() {
    for (const { el } of colRects) {
      el.addEventListener('dragover', (e) => {
        const tid = +(window._dragTaskId || 0);
        if (!tid) return;
        e.preventDefault();
        el.classList.add('droptarget');
        const start = snap(minAt({ el }, e.clientY), 30);
        const dur = planDuration(tid);
        if (!ghost) { ghost = document.createElement('div'); ghost.className = 'drop-ghost'; }
        if (ghost.parentNode !== el) el.appendChild(ghost);
        ghost.style.top = y(start) + 'px';
        ghost.style.height = y(dur) + 'px';
        ghost.textContent = `${minToHM(start)} · ${fmtDur(dur)}`;
        ghost.dataset.start = start;
      });
      el.addEventListener('dragleave', () => el.classList.remove('droptarget'));
      el.addEventListener('drop', (e) => {
        e.preventDefault();
        el.classList.remove('droptarget');
        const tid = +(e.dataTransfer.getData('text/task') || window._dragTaskId || 0);
        const start = +(ghost?.dataset.start ?? snap(minAt({ el }, e.clientY), 30));
        if (ghost) { ghost.remove(); ghost = null; }
        if (tid) H.onPlan(tid, el.dataset.date, start, planDuration(tid));
      });
    }
    root.addEventListener('dragend', () => { if (ghost) { ghost.remove(); ghost = null; } });
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
        if (!block || block.completed) { if (dist(e) === 0) {/* allow click */} }
        startDrag(e, ev, block);
      });
    }
  }
  function dist(e) { return 0; }

  function startDrag(e, el, block) {
    if (!block) return;
    e.preventDefault();
    const resizing = e.target.classList.contains('rs');
    const startMin0 = hmToMin(block.start_at.slice(11, 16));
    const endMin0 = hmToMin(block.end_at.slice(11, 16)) || 1440;
    const grabOffset = minAt(colAt(e.clientX) || colRects[0], e.clientY) - startMin0;
    let moved = false, cur = { date: block.start_at.slice(0, 10), s: startMin0, e: endMin0 };

    const onMove = (me) => {
      const col = colAt(me.clientX);
      if (!col) return;
      moved = true;
      el.classList.add('dragging');
      if (resizing) {
        const ne = Math.max(cur.s + 15, snap(minAt(col, me.clientY), 15));
        cur.e = Math.min(ne, 1440);
      } else {
        const dur = endMin0 - startMin0;
        let ns = snap(minAt(col, me.clientY) - grabOffset, 15);
        ns = Math.max(0, Math.min(ns, 1440 - dur));
        cur = { date: col.date, s: ns, e: ns + dur };
        if (col.el !== el.parentNode) col.el.appendChild(el);
      }
      el.style.top = y(cur.s) + 'px';
      el.style.height = y(cur.e - cur.s) + 'px';
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

  return { mount, render, setView };
})();
