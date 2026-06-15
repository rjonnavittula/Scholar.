/* calendar.js — the week. awake shading, activities, planned blocks,
   due flags, now line, drag-to-plan, move/resize. */
const Cal = (() => {
  const HOUR = 46;                       // px per hour — matches --hourH
  let root, S, H;                        // root el, state, handlers
  let colRects = [];                     // for pointer drag targeting

  const pad = (n) => String(n).padStart(2, '0');
  const minToHM = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const fmtDur = (m) => m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? pad(m % 60) : ''}` : `${m}m`;
  const y = (min) => (min / 60) * HOUR;
  const snap = (min, step = 15) => Math.round(min / step) * step;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function mount(el, state, handlers) { root = el; S = state; H = handlers; }

  function courseOf(task) { return S.courses.find((c) => c.id === task?.course_id); }
  function taskOf(id) { return S.tasks.find((t) => t.id === id); }

  // ---------- render ----------
  function render() {
    const days = S.weekDays;                       // [Date x7]
    const todayIso = S.todayIso;
    const avail = Object.fromEntries((S.availability || []).map((a) => [a.date, a]));

    let html = '<div class="cal-grid">';
    html += '<div class="cal-head gutter-cell"></div>';
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
    html += '<div class="gutter-cell">';
    for (let h = 0; h < 24; h++) html += `<div class="hour-label">${pad(h)}:00</div>`;
    html += '</div>';

    // day columns
    for (const d of days) {
      const iso = isoOf(d);
      const a = avail[iso] || { awake: [480, 1410] };
      const past = iso < todayIso;
      html += `<div class="day-col ${past ? 'past' : ''}" data-date="${iso}"
                    style="height:${24 * HOUR}px">`;
      for (let h = 1; h < 24; h++) html += `<div class="hour-line" style="top:${h * HOUR}px"></div>`;
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
      for (const p of S.planned.filter((x) => x.start_at.slice(0, 10) === iso)) {
        const t = taskOf(p.task_id) || {};
        const c = courseOf(t);
        const sMin = hmToMin(p.start_at.slice(11, 16));
        const eMin = hmToMin(p.end_at.slice(11, 16)) || 1440;
        html += evHtml({
          cls: 'planned' + (p.completed ? ' done' : ''), id: p.id,
          top: y(sMin), h: y(eMin - sMin), color: c?.color || '#8A7F73',
          title: t.title || '?', sub: `${minToHM(sMin)}–${minToHM(eMin)}`,
          resize: !p.completed,
        });
      }

      // due flags
      for (const t of S.tasks.filter((x) => x.status !== 'done'
          && x.due_at && x.due_at.slice(0, 10) === iso)) {
        const m = hmToMin(t.due_at.slice(11, 16));
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

  return { mount, render };
})();
