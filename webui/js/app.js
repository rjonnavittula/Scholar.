/* app.js — state, boot, sidebar, modals, glue. */
(() => {
  const $ = (id) => document.getElementById(id);
  const pad = (n) => String(n).padStart(2, '0');
  const isoOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const minToHM = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const fmtDur = (m) => { m = Math.abs(Math.round(m)); const h = Math.floor(m / 60), mm = m % 60;
    return h && mm ? `${h}h ${mm}m` : h ? `${h}h` : `${mm}m`; };
  const hmToMin = (hm) => { const [h, m] = hm.split(':').map(Number); return h * 60 + (m || 0); };
  const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
  const nowHM = () => { const n = new Date(); return `${pad(n.getHours())}:${pad(n.getMinutes())}`; };
  const plusHM = (mins) => { const n = new Date(Date.now() + mins * 60000); return `${pad(n.getHours())}:${pad(n.getMinutes())}`; };
  const PALETTE = ['#8A7F73', '#7A6A56', '#5F6B5A', '#6B5A66', '#56646E', '#7A5A4A', '#B59B5B'];
  const CATEGORIES = ['', 'Homework', 'Quiz', 'Exam', 'Project', 'Lab', 'Discussion', 'Reading', 'Other'];

  const S = {
    weekStart: mondayOf(new Date()),
    view: 'week', viewN: 7,
    get weekDays() {
      if (this.view === 'day') return [new Date(this.weekStart)];
      if (this.view === 'twoDay') return [new Date(this.weekStart), addDays(this.weekStart, 1)];
      if (this.view === 'nextN') return [...Array(this.viewN)].map((_, i) => addDays(new Date(), i));
      if (this.view === 'month') {
        // month view builds its own grid; return the month's weeks start
        return [...Array(7)].map((_, i) => addDays(this.weekStart, i));
      }
      return [...Array(7)].map((_, i) => addDays(this.weekStart, i));
    },
    get todayIso() { return isoOf(new Date()); },
    settings: {}, courses: [], activities: [], tasks: [], planned: [],
    cushion: null, cushionByTask: {}, availability: [], canvas: {},
  };

  function mondayOf(d) {
    const x = new Date(d); x.setHours(0, 0, 0, 0);
    x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
    return x;
  }
  function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }

  // ---------- boot ----------
  async function boot() {
    if (!Api.hasKey()) {
      const ok = await Api.ensureLocalDevKey();
      if (!ok) return showGate();
    }
    try { await Api.get('/config/settings'); } catch (e) { return showGate(); }
    $('gate').classList.add('hidden');
    $('app').classList.remove('hidden');
    Cal.mount($('calendar'), S, { onPlan, onMovePlanned, onBlockMenu, onMoveActivity, onActivityMenu });
    Panel.mount($('task-groups'), S, { onTaskAction, onPlanQuick, onTaskEdit });
    wireChrome();
    await loadAll();
    Pomo.restore();
    initTopbarResize();
    showGreeting();
  }
  function showGate() {
    $('gate').classList.remove('hidden');
    $('app').classList.add('hidden');
    $('gate-go').onclick = () => { Api.setKey($('gate-key').value.trim()); boot(); };
  }

  window.__S = S;
  async function loadAll() {
    const weekIso = isoOf(S.weekStart);
    const [settings, courses, activities, tasks, planned, cushion, avail, canvas, streak] =
      await Promise.all([
        Api.get('/config/settings'), Api.get('/courses'), Api.get('/activities'),
        Api.get('/tasks'), Api.get('/planned'), Api.get('/cushion'),
        Api.get(`/cushion/availability?start=${weekIso}&days=7`),
        Api.get('/integrations/canvas/status'),
        Api.get('/streak?days=7'),
      ]);
    Object.assign(S, { settings, courses, activities, tasks, planned, cushion,
                       availability: avail, canvas, streak });
    S.cushionByTask = Object.fromEntries((cushion.per_task || []).map((c) => [c.task_id, c]));
    renderAll();
    Timer.refresh();
  }

  function applyTheme() {
    const st = S.settings || {};
    document.body.classList.toggle('theme-light', st.theme === 'light');
    document.body.classList.toggle('theme-dark', st.theme !== 'light');
    const root = document.documentElement.style;
    if (st.accent) {
      root.setProperty('--accent', st.accent);
      // soft = accent at ~18% alpha
      root.setProperty('--accent-soft', hexA(st.accent, 0.18));
    }
    root.setProperty('--fontscale', st.fontscale || 1);
    root.setProperty('--density', st.density || 1);
  }
  function hexA(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${a})`;
  }

  function renderAll() {
    applyTheme();
    renderSidebar(); renderTop(); renderStreak(); Cal.render(); Panel.render();
    if ($('learn') && !$('learn').classList.contains('hidden')) renderHiveCourses();
    const list = document.getElementById('tasklist');
    if (list && !list.classList.contains('hidden')) renderTaskList(list);
  }

  // ---------- top chrome ----------
  function renderTop() {
    const a = S.weekDays[0], b = S.weekDays[S.weekDays.length - 1];
    $('week-label').textContent =
      `${a.toLocaleDateString(undefined, { month: 'long', day: 'numeric' })} – ` +
      `${b.toLocaleDateString(undefined, { month: b.getMonth() === a.getMonth() ? undefined : 'long', day: 'numeric' })}`;
    const chip = $('cushion-chip');
    const c = S.cushion || {};
    chip.textContent = `cushion ${c.total_cushion_human || '…'}`;
    chip.className = 'cushion-chip ' + (c.feasible ? 'ok' : 'bad');
  }

  // First open of the day: a full-screen time-of-day greeting that fades in,
  // holds, then fades away to reveal the app. Gated once per calendar day.
  function showGreeting() {
    const name = (S.settings && S.settings.display_name) || '';
    const today = new Date().toISOString().slice(0, 10);
    try {
      if (localStorage.getItem('scholar_greeted') === today) return;
      localStorage.setItem('scholar_greeted', today);
    } catch (e) { /* private mode — just show it */ }
    const h = new Date().getHours();
    const part = h < 5 ? 'Hello' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
    const ov = document.createElement('div');
    ov.className = 'greet-screen';
    ov.innerHTML = `<div class="greet-text">${esc(name ? `${part}, ${name}` : part)}</div>`;
    document.body.appendChild(ov);
    requestAnimationFrame(() => ov.classList.add('in'));
    const off = () => { ov.classList.remove('in'); setTimeout(() => ov.remove(), 600); };
    const t = setTimeout(off, 2400);
    ov.onclick = () => { clearTimeout(t); off(); };
  }

  // Collapse the two-tier top bar by its OWN width (not the window), so it
  // stays correct when the task panel opens/closes. Sets data-w on .topbar.
  function initTopbarResize() {
    const bar = document.querySelector('.topbar');
    const main = document.querySelector('.main');
    if (!bar || !main || typeof ResizeObserver === 'undefined') return;
    // Debounced: the sidebar/panel collapse buttons animate .main's width over
    // ~280ms, and an undebounced observer fires on every intermediate frame,
    // making the topbar's contents flicker in and out mid-transition. Only
    // apply the breakpoint once width has settled.
    let pending = null;
    const ro = new ResizeObserver((es) => {
      const w = es[0].contentRect.width;
      if (pending) clearTimeout(pending);
      pending = setTimeout(() => {
        pending = null;
        bar.dataset.w = w < 460 ? 'xs' : w < 560 ? 'sm' : w < 720 ? 'md' : 'full';
      }, 140);
    });
    ro.observe(main);
  }

  function renderStreak() {
    const el = document.getElementById('streak'); if (!el) return;
    const st = S.streak || { current: 0, days: [] };
    el.innerHTML = '<span class="flame">\u{1F525}</span>' +
      st.days.map((d) => `<span class="dot l${d.level}" title="${d.day}: ${d.score}"></span>`).join('') +
      `<span class="n">${st.current}d</span>`;
    el.style.cursor = 'pointer';
    el.title = 'study streak \u2014 open stats';
    el.onclick = () => showView('insights', document.querySelector('[data-view="insights"]'), 'streak');
  }

  function navBy(dir) {
    if (S.view === 'month') {
      const d = new Date(S.weekStart);
      S.weekStart = new Date(d.getFullYear(), d.getMonth() + dir, 1);
    } else {
      const n = S.view === 'nextN' ? (S.viewN || 7) : S.view === 'twoDay' ? 2 : 7;
      S.weekStart = addDays(S.weekStart, dir * n);
    }
    loadAll();
  }

  function setCalView(view) {
    S.view = view;
    if (view === 'twoDay') { const t = new Date(); S.weekStart = new Date(t.getFullYear(), t.getMonth(), t.getDate()); }
    for (const b of document.querySelectorAll('#viewtabs [data-view]'))
      b.classList.toggle('active', b.dataset.view === view);
    if (view !== 'nextN') document.getElementById('view-n').value = '';
    Cal.setView ? Cal.setView(view, S.viewN || 7) : null;
    loadAll();
  }

  function wireChrome() {
    const cl = document.getElementById('collapse-left');
    const cr = document.getElementById('collapse-right');
    const afterCollapse = () => { setTimeout(() => Cal.resize && Cal.resize(), 320); };
    if (cl) cl.onclick = () => { document.body.classList.toggle('no-left');
      cl.textContent = document.body.classList.contains('no-left') ? '›' : '‹'; afterCollapse(); };
    if (cr) cr.onclick = () => { document.body.classList.toggle('no-right');
      cr.textContent = document.body.classList.contains('no-right') ? '‹' : '›'; afterCollapse(); };
    for (const b of document.querySelectorAll('#viewtabs [data-view]'))
      b.onclick = () => setCalView(b.dataset.view);
    const vn = document.getElementById('view-n');
    if (vn) vn.onchange = () => { if (vn.value) { S.viewN = +vn.value; setCalView('nextN'); } };
    $('nav-today').onclick = () => { S.weekStart = mondayOf(new Date()); loadAll(); };
    $('nav-prev').onclick = () => { navBy(-1); };
    $('nav-next').onclick = () => { navBy(1); };
    $('btn-add-task').onclick = () => taskModal();
    const pomoBtn = $('btn-pomodoro');
    if (pomoBtn) pomoBtn.onclick = () => pomodoroModal();

    // task panel: sort popover + calculate-cushion button
    const sortBtn = $('btn-sort'), sortPop = $('sort-pop');
    if (sortBtn) sortBtn.onclick = (e) => { e.stopPropagation(); sortPop.classList.toggle('hidden'); };
    document.addEventListener('click', (e) => {
      if (sortPop && !sortPop.classList.contains('hidden')
          && !sortPop.contains(e.target) && e.target !== sortBtn) sortPop.classList.add('hidden');
    });
    for (const b of document.querySelectorAll('#sort-pop .sk')) b.onclick = () => {
      document.querySelectorAll('#sort-pop .sk').forEach((x) => x.classList.toggle('on', x === b));
      Panel.setSort(b.dataset.sk, null);
    };
    for (const r of document.querySelectorAll('#sort-pop input[name=sdir]'))
      r.onchange = () => Panel.setSort(null, r.value);
    const cushBtn = $('btn-cushion');
    if (cushBtn) cushBtn.onclick = recalcCushion;
    $('btn-add-course').onclick = () => courseModal();
    $('btn-add-activity').onclick = () => activityModal();
    $('btn-canvas-cfg').onclick = () => canvasModal();
    $('btn-canvas-sync').onclick = syncCanvas;
    for (const b of document.querySelectorAll('#btn-settings, #btn-settings-mobile')) b.onclick = () => settingsModal();
    const themeBtns = [...document.querySelectorAll('#btn-theme, #btn-theme-mobile')];
    if (themeBtns.length) {
      const paintThemeIcon = () => { for (const b of themeBtns) b.textContent = (S.settings.theme === 'light') ? '☀' : '☽'; };
      paintThemeIcon();
      const onThemeClick = async () => {
        const next = (S.settings.theme === 'light') ? 'dark' : 'light';
        S.settings.theme = next;
        applyTheme(); paintThemeIcon();
        try { await Api.put('/config/settings', { theme: next }); } catch (e) {}
      };
      for (const b of themeBtns) b.onclick = onThemeClick;
    }
    // Both the rail and the mobile bottom nav share these data-view buttons.
    for (const b of document.querySelectorAll('[data-view="insights"]')) b.onclick = (e) => showView('insights', e.currentTarget);
    for (const b of document.querySelectorAll('[data-view="home"]')) b.onclick = (e) => showView('home', e.currentTarget);
    for (const b of document.querySelectorAll('[data-view="learn"]')) b.onclick = (e) => showView('learn', e.currentTarget);
  }


  // ---------- sidebar ----------
  function courseOrder() {
    try { return JSON.parse(localStorage.getItem('scholar_course_order') || '[]'); } catch (e) { return []; }
  }
  function saveCourseOrder(ids) { localStorage.setItem('scholar_course_order', JSON.stringify(ids)); }
  function sortedCourses() {
    const order = courseOrder();
    const rank = new Map(order.map((id, i) => [id, i]));
    return S.courses.slice().sort((a, b) => {
      const ra = rank.has(a.id) ? rank.get(a.id) : Infinity;
      const rb = rank.has(b.id) ? rank.get(b.id) : Infinity;
      return ra - rb || a.id - b.id;
    });
  }

  function renderSidebar() {
    $('course-list').innerHTML = sortedCourses().map((c) => `
      <div class="side-item clickable" draggable="true" data-edit-course="${c.id}" data-cid="${c.id}">
        <span class="dot" style="background:${c.color}"></span>
        <span class="nm">${esc(c.name)}</span>
        ${c.source === 'canvas' ? '<span class="meta">canvas</span>' : ''}
        <button class="x" data-del-course="${c.id}">✕</button>
      </div>`).join('') || '<p class="muted small">no courses yet</p>';
    wireCourseReorder();

    const actGroups = {};
    for (const a of S.activities) {
      const k = `${a.title}|${a.start_min}|${a.end_min}|${a.color}`;
      (actGroups[k] ??= { ...a, ids: [], days: [] });
      actGroups[k].ids.push(a.id);
      actGroups[k].days.push(a.weekday);
    }
    const FULL = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const dayLabel = (ds) => {
      const s = [...new Set(ds)].sort((a, b) => a - b);
      if (s.length === 7) return 'Daily';
      if (s.length === 5 && s.every((d, i) => d === i)) return 'Weekdays';
      if (s.length === 2 && s[0] === 5 && s[1] === 6) return 'Weekends';
      const contig = s.every((d, i) => i === 0 || d === s[i - 1] + 1);
      if (contig && s.length >= 3) return `${FULL[s[0]]}\u2013${FULL[s[s.length - 1]]}`;
      return s.map((d) => FULL[d]).join(' ');
    };
    const fmt12 = (m) => { const h = Math.floor(m / 60); return `${((h + 11) % 12) + 1}:${pad(m % 60)} ${h < 12 ? 'AM' : 'PM'}`; };
    $('activity-list').innerHTML = Object.values(actGroups)
      .sort((a, b) => Math.min(...a.days) - Math.min(...b.days) || a.start_min - b.start_min)
      .map((g) => `
      <div class="side-item act clickable" draggable="true" data-edit-act="${g.ids.join(',')}"
           data-title="${esc(g.title)}" data-color="${g.color}" data-course-id="${g.course_id ?? ''}"
           data-days="${g.days.join(',')}" data-s="${g.start_min}" data-e="${g.end_min}">
        <span class="dot" style="background:${g.color}"></span>
        <span class="side-txt">
          <span class="nm" title="${esc(g.title)}">${esc(g.title)}</span>
          <span class="meta">${dayLabel(g.days)} \u00b7 ${fmt12(g.start_min)}\u2013${fmt12(g.end_min)}</span>
        </span>
        <button class="x" data-del-act="${g.ids.join(',')}">\u2715</button>
      </div>`).join('') || '<p class="muted small">no activities yet</p>';
    wireActivityDrag();

    $('canvas-status').textContent = S.canvas.configured
      ? `linked · ${S.canvas.base_url.replace(/^https?:\/\//, '')}`
      : (S.canvas.ics_configured ? 'calendar feed linked' : 'not configured');
    $('btn-canvas-sync').classList.toggle('hidden', !S.canvas.configured);

    for (const b of document.querySelectorAll('[data-del-course]'))
      b.onclick = async () => { if (confirm('Delete course (and keep its tasks)?'))
        { await Api.del('/courses/' + b.dataset.delCourse); loadAll(); } };
    for (const b of document.querySelectorAll('[data-del-act]'))
      b.onclick = async () => {
        const ids = b.dataset.delAct.split(',');
        await Promise.all(ids.map((id) => Api.del('/activities/' + id)));
        loadAll();
      };

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
          course_id: row.dataset.courseId ? +row.dataset.courseId : null,
        }); };
  }

  // ---------- course sidebar drag-to-reorder ----------
  function wireCourseReorder() {
    let draggedId = null;
    const rows = document.querySelectorAll('#course-list [data-cid]');
    for (const row of rows) {
      row.addEventListener('dragstart', (e) => {
        draggedId = +row.dataset.cid;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/course', String(draggedId));
        row.classList.add('dragging');
      });
      row.addEventListener('dragend', () => row.classList.remove('dragging'));
      row.addEventListener('dragover', (e) => {
        if (draggedId == null) return;
        e.preventDefault();
        row.classList.toggle('drop-before', e.clientY < row.getBoundingClientRect().top + row.offsetHeight / 2);
        row.classList.toggle('drop-after', e.clientY >= row.getBoundingClientRect().top + row.offsetHeight / 2);
      });
      row.addEventListener('dragleave', () => row.classList.remove('drop-before', 'drop-after'));
      row.addEventListener('drop', (e) => {
        e.preventDefault();
        row.classList.remove('drop-before', 'drop-after');
        const targetId = +row.dataset.cid;
        if (draggedId == null || draggedId === targetId) return;
        const before = e.clientY < row.getBoundingClientRect().top + row.offsetHeight / 2;
        const ids = sortedCourses().map((c) => c.id).filter((id) => id !== draggedId);
        const idx = ids.indexOf(targetId);
        ids.splice(before ? idx : idx + 1, 0, draggedId);
        saveCourseOrder(ids);
        draggedId = null;
        renderSidebar();
      });
    }
  }

  // ---------- activity drag-to-retime on the calendar ----------
  function wireActivityDrag() {
    for (const row of document.querySelectorAll('#activity-list [data-edit-act]')) {
      row.addEventListener('dragstart', (e) => {
        window._dragActivity = {
          ids: row.dataset.editAct.split(',').map(Number),
          title: row.dataset.title, color: row.dataset.color,
          days: row.dataset.days.split(',').map(Number),
          durationMin: (+row.dataset.e) - (+row.dataset.s),
          course_id: row.dataset.courseId ? +row.dataset.courseId : null,
        };
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/activity', row.dataset.editAct);
      });
      row.addEventListener('dragend', () => { window._dragActivity = null; });
    }
  }

  // Dropping an activity places/retimes just the ONE day you dropped it on
  // (like planning a task) — every other day already in its pattern is left
  // untouched, and dropping on a day it didn't previously occur on adds it.
  async function onMoveActivity(act, newStartMin, newEndMin, weekday) {
    const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    try {
      if (act.ids.length === 1) {
        // dragging/resizing a single concrete occurrence directly on the
        // calendar — update it in place (same id, atomic PATCH), including
        // a weekday change if it was dragged into a different column. No
        // delete+recreate here: that pattern is what let a double-fired
        // drag (or any retry) silently leave a duplicate behind, since
        // DELETE on an already-gone id is a harmless no-op server-side.
        await Api.patch('/activities/' + act.ids[0], { weekday, start_min: newStartMin, end_min: newEndMin });
      } else {
        // dragging the sidebar card for a multi-day group — only the one
        // day you dropped on changes; every other day stays put. If that
        // day already has an occurrence, patch it in place; only a
        // genuinely new day (not yet in the pattern) needs a fresh row.
        const idx = act.days.indexOf(weekday);
        if (idx !== -1) {
          await Api.patch('/activities/' + act.ids[idx], { start_min: newStartMin, end_min: newEndMin });
        } else {
          await Api.post('/activities', { title: act.title, color: act.color, weekday, start_min: newStartMin, end_min: newEndMin, course_id: act.course_id ?? null });
        }
      }
      await loadAll();
      toast(`${act.title} · ${DAY_NAMES[weekday]} · ${minToHM(newStartMin)}–${minToHM(newEndMin)}`);
    } catch (e) { toast('could not place activity', true); loadAll(); }
  }

  async function syncCanvas() {
    const btn = $('btn-canvas-sync');
    btn.textContent = '↻ syncing…'; btn.disabled = true;
    try {
      const r = await Api.post('/integrations/canvas/sync');
      toast(`canvas: ${r.created} new, ${r.updated} updated across ${r.courses} courses`);
      await loadAll();
    } catch (e) { toast(e.message, true); }
    btn.textContent = '↻ sync now'; btn.disabled = false;
  }

  // ---------- calendar handlers ----------
  function localIso(dateIso, min) { return `${dateIso}T${minToHM(min)}:00`; }

  function onTaskEdit(taskId) {
    const t = S.tasks.find((x) => x.id === taskId);
    if (t) taskModal(t);
  }

  async function recalcCushion() {
    const btn = $('btn-cushion');
    if (btn) { btn.classList.add('busy'); btn.disabled = true; }
    try {
      const weekIso = isoOf(S.weekStart);
      const [cushion, avail] = await Promise.all([
        Api.get('/cushion'),
        Api.get(`/cushion/availability?start=${weekIso}&days=7`),
      ]);
      S.cushion = cushion; S.availability = avail;
      S.cushionByTask = Object.fromEntries((cushion.per_task || []).map((c) => [c.task_id, c]));
      renderTop(); Panel.render();
      toast('cushion recalculated');
    } catch (e) { toast('cushion calc failed'); }
    finally { if (btn) { btn.classList.remove('busy'); btn.disabled = false; } }
  }

  async function onPlanQuick(taskId) {
    const t = S.tasks.find((x) => x.id === taskId); if (!t) return;
    // default: today, next half-hour, full remaining time (cap 2h for first block)
    const now = new Date();
    const start = Math.min(1410, (now.getHours() * 60 + now.getMinutes() + 30) - ((now.getMinutes() + 30) % 30) + 30);
    const rem = Math.max(30, (t.time_needed_min || 60) - (t.time_spent_min || 0));
    planExactDialog(t, isoOf(now), start, Math.min(rem, 120));
  }

  // Type exact day / time / duration to place a block precisely.
  function planExactDialog(t, dateIso, startMin, durMin) {
    modal(`
      <h2>plan \u00b7 ${esc(t.title)}</h2>
      <div class="frow">
        <div><label>day</label><input id="p-d" type="date" value="${dateIso}" /></div>
        <div><label>start</label><input id="p-t" type="time" value="${minToHM(startMin)}" /></div>
        <div><label>minutes</label><input id="p-dur" type="text" inputmode="numeric" value="${durMin}" /></div>
      </div>
      <p class="muted small">tip: after placing, drag the block on the calendar to move or resize it.</p>
      ${ACTIONS('place')}`, async (act, ov) => {
      if (act !== 'save') return;
      const d = ov.querySelector('#p-d').value;
      const start = hmToMin(ov.querySelector('#p-t').value);
      const dur = Math.max(15, parseInt(ov.querySelector('#p-dur').value || '60', 10) || 60);
      if (d) { await onPlan(t.id, d, start, dur); }
    });
  }

  async function onPlan(taskId, dateIso, startMin, durMin) {
    try {
      await Api.post('/planned', {
        task_id: taskId,
        start_at: localIso(dateIso, startMin),
        end_at: localIso(dateIso, Math.min(startMin + durMin, 1439)),
      });
      await loadAll();
    } catch (e) { toast(e.message, true); }
  }

  async function onMovePlanned(pid, dateIso, sMin, eMin) {
    try {
      await Api.patch('/planned/' + pid, {
        start_at: localIso(dateIso, sMin), end_at: localIso(dateIso, eMin),
      });
      await loadAll();
    } catch (e) { toast(e.message, true); }
  }

  // ---------- global persistent timer ----------
  // One timer at a time, server-backed so it survives reload. The pill in the
  // top bar ticks from started_at; clicking it reopens the modal.
  const Timer = {
    state: { running: false },
    paused: false,
    _tick: null,

    async refresh() {
      try { this.state = await Api.get('/timer'); } catch { this.state = { running: false }; }
      this.paused = !!this.state.paused;
      this.render();
    },

    async start(taskId, title) {
      // warn if another timer is running for a different task
      if (this.state.running && this.state.task_id !== taskId) {
        const cur = this.state.title || 'another task';
        if (!confirm(`You're timing "${cur}". Stop it and start timing "${title}"?`)) return false;
        await Api.post('/timer/stop'); await loadAll();
      }
      let r;
      try { r = await Api.post('/timer/start?task_id=' + taskId); }
      catch (e) { toast('timer failed: ' + e.message, true); return false; }
      if (!r || !r.task_id) { toast('timer failed to start', true); return false; }
      this.paused = false;
      this.state = { ...r, running: true };
      this.render();
      return true;
    },

    async pause() {
      await Api.post('/timer/pause');
      this.paused = true;
      await this.refresh();
    },

    async resume() {
      await Api.post('/timer/resume');
      this.paused = false;
      await this.refresh();
    },

    async stop() {
      const r = await Api.post('/timer/stop');
      this.state = { running: false };
      this.paused = false;
      this.render();
      await loadAll();
      if (r.logged_min > 0) toast(`logged ${r.logged_min} min`);
      return r;
    },

    // discard the current session — clears the timer, logs nothing
    async cancel() {
      await Api.post('/timer/cancel');
      this.state = { running: false };
      this.paused = false;
      this.render();
    },

    elapsedSec() {
      if (!this.state.running) return 0;
      const base = this.state.accumulated_sec || 0;
      if (this.paused || this.state.paused) return base;
      const start = new Date(this.state.started_at).getTime();
      return base + Math.max(0, Math.floor((Date.now() - start) / 1000));
    },

    fmt(s) {
      return [s / 3600, (s % 3600) / 60, s % 60]
        .map((n) => String(Math.floor(n)).padStart(2, '0')).join(':');
    },

    render() {
      window.__TIMER = this.state.running ? { ...this.state, paused: this.paused } : { running: false };
      let pill = document.getElementById('timer-pill');
      if (!this.state.running) {
        if (pill) pill.remove();
        if (this._tick) { clearInterval(this._tick); this._tick = null; }
        return;
      }
      if (!pill) {
        pill = document.createElement('button');
        pill.id = 'timer-pill';
        pill.className = 'timer-pill';
        pill.onclick = () => timerModal(S.tasks.flatMap((t) => [t, ...(t.subtasks || [])])
          .find((x) => x.id === this.state.task_id) || { id: this.state.task_id, title: this.state.title });
        const anchor = document.getElementById('topbar-actions') || document.querySelector('.topbar');
        anchor.insertBefore(pill, anchor.firstChild);
      }
      this.paintPill();
      this.startTicker();
    },

    paintPill() {
      const pill = document.getElementById('timer-pill');
      if (!pill || !this.state.running) return;
      const txt = this.fmt(this.elapsedSec());
      pill.innerHTML = `<span class="tp-dot ${this.paused ? 'paused' : ''}"></span>\u23F1 ${txt}`;
      const chip = document.querySelector(`[data-timing="${this.state.task_id}"]`);
      if (chip) chip.innerHTML = `<span class="tp-dot"></span>${txt}`;
      // live update any open modal stopwatch
      const read = document.getElementById('t-read');
      if (read && read.dataset.tid == this.state.task_id) read.textContent = txt;
    },

    // one persistent ticker for the whole app; repaints every second while
    // a timer runs and is not paused. Never stacked, never cleared by renders.
    startTicker() {
      if (this._tick) return;
      this._tick = setInterval(() => {
        if (!this.state.running || this.paused || this.state.paused) return;
        this.paintPill();
      }, 1000);
    },
  };

  // ---------- Pomodoro ----------
  // A focus/break cycler layered on real logging: each completed (or stopped)
  // focus phase logs its elapsed minutes to the task via /tasks/{id}/log. Runs
  // on its own ticker independent of the modal, and resumes across reloads.
  const POMO_PRESETS = [15, 25, 50];
  const Pomo = {
    cfg: { work: 25, shortBreak: 5, longBreak: 15, cycles: 4, autostart: true, muted: false },
    st: { phase: 'idle', taskId: null, taskTitle: '', endsAt: 0, remaining: 0, paused: false, cycle: 0 },
    _tick: null, _ac: null,

    loadCfg() {
      try { Object.assign(this.cfg, JSON.parse(localStorage.getItem('scholar_pomo_cfg') || '{}')); } catch (e) { /* defaults */ }
    },
    saveCfg() { localStorage.setItem('scholar_pomo_cfg', JSON.stringify(this.cfg)); },
    save() { localStorage.setItem('scholar_pomo', JSON.stringify(this.st)); },
    restore() {
      this.loadCfg();
      try {
        const s = JSON.parse(localStorage.getItem('scholar_pomo') || 'null');
        if (s && s.phase && s.phase !== 'idle') {
          this.st = s;
          if (!s.paused && s.endsAt) { if (Date.now() >= s.endsAt) this._end(); else this._ensureTicker(); }
        }
      } catch (e) { /* ignore */ }
      this._paintBtn();
    },

    dur(phase) { return ({ work: this.cfg.work, break: this.cfg.shortBreak, long: this.cfg.longBreak }[phase] || 0) * 60000; },
    label(phase) { return ({ work: 'Focus', break: 'Short break', long: 'Long break', idle: 'Ready' }[phase || this.st.phase]); },
    running() { return this.st.phase !== 'idle'; },
    remainingMs() {
      if (this.st.phase === 'idle') return 0;
      return this.st.paused ? this.st.remaining : Math.max(0, this.st.endsAt - Date.now());
    },
    fmt(ms) {
      const s = Math.max(0, Math.round(ms / 1000));
      return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    },

    start(taskId, taskTitle) {
      if (!taskId) { toast('pick a task to focus on', true); return; }
      this.loadCfg();
      this.st = { phase: 'work', taskId, taskTitle: taskTitle || '', endsAt: 0, remaining: 0, paused: false, cycle: 0 };
      this._reqNotify();
      this._begin('work', true);
    },
    _begin(phase, fresh) {
      this.st.phase = phase;
      this.st.endsAt = Date.now() + this.dur(phase);
      this.st.paused = false; this.st.remaining = 0;
      this.save(); this._ensureTicker(); this.render();
      if (!fresh) this._notify(phase === 'work' ? 'Back to focus \u2014 ' + (this.st.taskTitle || 'study')
                                                : (phase === 'long' ? 'Long break \u2014 step away' : 'Break time \u2014 rest a bit'));
    },
    _arm(phase) {                       // next phase ready but waiting (autostart off)
      this.st.phase = phase; this.st.paused = true;
      this.st.remaining = this.dur(phase); this.st.endsAt = 0;
      this.save(); this.render();
      this._notify(phase === 'work' ? 'Ready to focus when you are' : 'Time for a break');
    },
    _ensureTicker() {
      if (this._tick) return;
      this._tick = setInterval(() => {
        if (this.st.phase === 'idle') return this._stopTicker();
        if (!this.st.paused && Date.now() >= this.st.endsAt) this._end(); else this.render();
      }, 250);
    },
    _stopTicker() { if (this._tick) { clearInterval(this._tick); this._tick = null; } },

    async _logWork(elapsedMs) {
      const m = Math.round(elapsedMs / 60000);
      if (m < 1 || !this.st.taskId) return;
      try { await Api.post(`/tasks/${this.st.taskId}/log?minutes=${m}`); await loadAll(); } catch (e) { /* keep cycling */ }
    },
    _end() {
      if (this.st.phase === 'work') {
        this._logWork(this.dur('work'));
        this.st.cycle += 1;
        const next = (this.st.cycle % this.cfg.cycles) === 0 ? 'long' : 'break';
        if (this.cfg.autostart) this._begin(next, false); else this._arm(next);
      } else {
        if (this.cfg.autostart) this._begin('work', false); else this._arm('work');
      }
    },
    pauseToggle() {
      if (this.st.phase === 'idle') return;
      if (this.st.paused) {
        this.st.endsAt = Date.now() + (this.st.remaining || this.dur(this.st.phase));
        this.st.remaining = 0; this.st.paused = false; this._ensureTicker();
      } else { this.st.remaining = this.remainingMs(); this.st.paused = true; }
      this.save(); this.render();
    },
    skip() {
      if (this.st.phase === 'idle') return;
      if (this.st.phase === 'work') this._logWork(this.dur('work') - this.remainingMs());
      if (this.st.phase === 'work') {
        this.st.cycle += 1;
        const next = (this.st.cycle % this.cfg.cycles) === 0 ? 'long' : 'break';
        if (this.cfg.autostart) this._begin(next, false); else this._arm(next);
      } else if (this.cfg.autostart) this._begin('work', false); else this._arm('work');
    },
    stop() {
      if (this.st.phase === 'work') this._logWork(this.dur('work') - this.remainingMs());
      this.st = { phase: 'idle', taskId: null, taskTitle: '', endsAt: 0, remaining: 0, paused: false, cycle: 0 };
      this._stopTicker(); this.save(); this.render();
    },

    _reqNotify() { try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); } catch (e) { /* */ } },
    _notify(msg) {
      toast(msg);
      try { if ('Notification' in window && Notification.permission === 'granted') new Notification('scholar', { body: msg }); } catch (e) { /* */ }
      this._beep();
    },
    _beep() {
      if (this.cfg.muted) return;
      try {
        const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
        const ac = this._ac || (this._ac = new AC());
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'sine'; o.frequency.value = 660; g.gain.value = 0.06;
        o.connect(g); g.connect(ac.destination); o.start(); o.stop(ac.currentTime + 0.18);
      } catch (e) { /* ignore */ }
    },

    _paintBtn() { const b = $('btn-pomodoro'); if (b) b.classList.toggle('on', this.running()); },
    render() {
      this._paintBtn();
      const clock = $('pomo-clock'); if (!clock) return;     // modal not open
      const phase = this.st.phase;
      const idle = phase === 'idle';
      const ph = $('pomo-phase'); ph.textContent = this.label(); ph.className = 'pomo-phase ' + phase;
      clock.textContent = idle ? this.fmt(this.dur('work')) : this.fmt(this.remainingMs());
      clock.classList.toggle('paused', this.st.paused && !idle);

      const ringWrap = $('pomo-ring-wrap');
      const ringFill = $('pomo-ring-fill');
      if (ringWrap && ringFill) {
        ringWrap.className = 'pomo-ring-wrap ' + phase;
        const circumference = ringFill.r.baseVal.value * 2 * Math.PI;
        const total = idle ? this.dur('work') : this.dur(phase);
        const fraction = idle ? 1 : Math.max(0, Math.min(1, this.remainingMs() / (total || 1)));
        ringFill.style.strokeDasharray = `${circumference}`;
        ringFill.style.strokeDashoffset = `${circumference * (1 - fraction)}`;
      }

      const dots = $('pomo-dots');
      if (dots) {
        const done = this.st.cycle % this.cfg.cycles;
        dots.innerHTML = Array.from({ length: this.cfg.cycles }, (_, i) =>
          `<span class="pdot ${i < done ? 'on' : ''} ${(phase === 'work' && i === done) ? 'live' : ''}"></span>`).join('');
      }
      const sessLbl = $('pomo-session-lbl');
      if (sessLbl) sessLbl.textContent = `session ${(this.st.cycle % this.cfg.cycles) + 1} of ${this.cfg.cycles}`;

      const wrap = $('pomo-controls');
      if (wrap) {
        wrap.querySelector('#pm-start').style.display = idle ? '' : 'none';
        wrap.querySelector('#pm-pause').style.display = idle ? 'none' : '';
        wrap.querySelector('#pm-skip').style.display = idle ? 'none' : '';
        wrap.querySelector('#pm-stop').style.display = idle ? 'none' : '';
        wrap.querySelector('#pm-pause').textContent = this.st.paused ? 'resume' : 'pause';
      }
      const picker = $('pomo-task'); if (picker) picker.disabled = !idle;
      const presets = document.querySelectorAll('.pomo-presets [data-preset]');
      for (const b of presets) b.classList.toggle('on', +b.dataset.preset === this.cfg.work);
      const muteBtn = $('pomo-mute');
      if (muteBtn) {
        muteBtn.classList.toggle('on', this.cfg.muted);
        muteBtn.textContent = this.cfg.muted ? '🔕' : '🔔';
        muteBtn.title = this.cfg.muted ? 'sound off — click to unmute' : 'sound on — click to mute';
      }
    },
  };

  function clampInt(v, lo, hi, dflt) { v = parseInt(v, 10); if (isNaN(v)) return dflt; return Math.max(lo, Math.min(hi, v)); }

  function pomodoroModal() {
    Pomo.loadCfg();
    const open = S.tasks.filter((t) => t.status !== 'done');
    const curId = Pomo.st.taskId || (Timer.state && Timer.state.running ? Timer.state.task_id : null) || (open[0] && open[0].id);
    const taskOpts = open.map((t) => `<option value="${t.id}" ${t.id === curId ? 'selected' : ''}>${esc(t.title)}</option>`).join('');
    const c = Pomo.cfg;
    const RING_R = 56;
    const html = `
      <div class="pomo">
        <div class="pomo-ring-wrap ${Pomo.st.phase}" id="pomo-ring-wrap">
          <svg class="pomo-ring" viewBox="0 0 120 120">
            <circle class="ring-track" cx="60" cy="60" r="${RING_R}"></circle>
            <circle class="ring-fill" id="pomo-ring-fill" cx="60" cy="60" r="${RING_R}"></circle>
          </svg>
          <div class="pomo-ring-center">
            <div class="pomo-phase ${Pomo.st.phase}" id="pomo-phase">${Pomo.label()}</div>
            <div class="pomo-clock" id="pomo-clock">${Pomo.fmt(Pomo.running() ? Pomo.remainingMs() : Pomo.dur('work'))}</div>
          </div>
        </div>
        <div class="pomo-dots" id="pomo-dots"></div>
        <div class="pomo-session-lbl" id="pomo-session-lbl"></div>
        <label class="pomo-task-row">focus on
          <select id="pomo-task">${taskOpts || '<option value="">no open tasks</option>'}</select>
        </label>
        <div class="pomo-controls" id="pomo-controls">
          <button class="primary" id="pm-start">start</button>
          <button id="pm-pause">pause</button>
          <button id="pm-skip">skip</button>
          <button id="pm-stop" class="danger">stop</button>
        </div>
        <div class="pomo-foot">
          <details class="pomo-settings">
            <summary>settings</summary>
            <div class="pomo-presets" id="pomo-presets">
              ${POMO_PRESETS.map((m) => `<button data-preset="${m}" type="button">${m}m</button>`).join('')}
            </div>
            <div class="pomo-grid">
              <label>focus<input type="number" min="1" max="180" id="ps-work" value="${c.work}"></label>
              <label>short break<input type="number" min="1" max="60" id="ps-short" value="${c.shortBreak}"></label>
              <label>long break<input type="number" min="1" max="90" id="ps-long" value="${c.longBreak}"></label>
              <label>cycles<input type="number" min="1" max="12" id="ps-cycles" value="${c.cycles}"></label>
            </div>
            <label class="pomo-auto"><input type="checkbox" id="ps-auto" ${c.autostart ? 'checked' : ''}> auto-start next phase</label>
          </details>
          <button class="pomo-mute" id="pomo-mute" type="button"></button>
        </div>
      </div>`;
    const { ov } = modal(html);
    ov.querySelector('#pm-start').onclick = () => {
      const sel = ov.querySelector('#pomo-task');
      Pomo.start(+(sel && sel.value), sel && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : '');
    };
    ov.querySelector('#pm-pause').onclick = () => Pomo.pauseToggle();
    ov.querySelector('#pm-skip').onclick = () => Pomo.skip();
    ov.querySelector('#pm-stop').onclick = () => Pomo.stop();
    ov.querySelector('#pomo-mute').onclick = () => { Pomo.cfg.muted = !Pomo.cfg.muted; Pomo.saveCfg(); Pomo.render(); };
    const saveCfg = () => {
      Pomo.cfg.work = clampInt(ov.querySelector('#ps-work').value, 1, 180, 25);
      Pomo.cfg.shortBreak = clampInt(ov.querySelector('#ps-short').value, 1, 60, 5);
      Pomo.cfg.longBreak = clampInt(ov.querySelector('#ps-long').value, 1, 90, 15);
      Pomo.cfg.cycles = clampInt(ov.querySelector('#ps-cycles').value, 1, 12, 4);
      Pomo.cfg.autostart = ov.querySelector('#ps-auto').checked;
      Pomo.saveCfg();
      if (!Pomo.running()) Pomo.render();
    };
    for (const el of ov.querySelectorAll('.pomo-settings input')) el.onchange = saveCfg;
    for (const b of ov.querySelectorAll('.pomo-presets [data-preset]')) {
      b.onclick = () => { ov.querySelector('#ps-work').value = b.dataset.preset; saveCfg(); };
    }
    Pomo.render();
  }

  function onBlockMenu(block) {
    const t = S.tasks.find((x) => x.id === block.task_id) || {};
    timerModal(t, block);
  }

  // Same grouping key renderSidebar/courseClassGroups use, so clicking an
  // activity block on the calendar opens the exact same edit view as
  // clicking its row in the sidebar.
  function activityGroupFor(a) {
    const key = (x) => `${x.title}|${x.start_min}|${x.end_min}|${x.color}`;
    const matches = S.activities.filter((x) => key(x) === key(a));
    return {
      ids: matches.map((x) => x.id), title: a.title, color: a.color,
      days: matches.map((x) => x.weekday),
      start_min: a.start_min, end_min: a.end_min, course_id: a.course_id ?? null,
    };
  }
  function onActivityMenu(actId) {
    const a = S.activities.find((x) => x.id === actId);
    if (!a) return;
    const course = a.course_id ? S.courses.find((c) => c.id === a.course_id) : null;
    activityModal(activityGroupFor(a), course ? { courseCtx: course } : undefined);
  }

  // The timer modal reflects the GLOBAL timer. It shows what you're timing
  // (task or subtask, with its parent), logs on stop, and completing is separate.
  function timerModal(t, block) {
    if (!t || !t.id) return;
    const subs = (t.subtasks || []);
    const hasSubs = subs.length > 0;
    const family = [t, ...subs];
    const parent = t.parent_id ? S.tasks.find((x) => x.id === t.parent_id) : null;
    const course = t.course_id ? S.courses.find((c) => c.id === t.course_id) : null;
    const activeId = () => (Timer.state.running ? Timer.state.task_id : null);
    const familyActive = () => family.find((x) => x.id === activeId());
    const homeTz = (S.settings && S.settings.home_tz) || 'America/New_York';

    // header: course · category  (falls back to "subtask of …" when nested)
    const crumb = parent
      ? `\u21B3 part of ${esc(parent.title)}`
      : [course ? esc(course.name) : '', t.category ? esc(t.category) : '']
          .filter(Boolean).join('  \u00b7  ') || 'task';

    // Start pill — the planned block's start, else the task's start date
    let startTxt = '\u2014';
    if (block) {
      startTxt = Api.fmtInZone(block.start_at, homeTz,
        { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true })
        .replace(' PM', 'pm').replace(' AM', 'am');
    } else if (t.start_date) {
      startTxt = new Date(t.start_date + 'T00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
    // Time-planned pill — "1h 00m"
    const need = t.time_needed_min || 0;
    const plannedTxt = `${Math.floor(need / 60)}h ${String(need % 60).padStart(2, '0')}m`;

    const directMin = (t.direct_spent_min != null) ? t.direct_spent_min : (hasSubs ? 0 : (t.time_spent_min || 0));
    const totalMin = t.time_spent_min || 0;

    const breakdown = hasSubs ? `
      <div class="t-breakdown">
        <div class="tb-head"><span class="muted small">total</span>
          <strong>${fmtDur(totalMin)}</strong>
          <span class="muted small">/ ${fmtDur(need)} planned</span></div>
        <div class="tb-row" data-tid="${t.id}">
          <button class="tb-play" data-play="${t.id}">\u25B6</button>
          <span class="tb-label">this task \u00b7 directly</span>
          <span class="tb-time">${fmtDur(directMin)}</span>
        </div>
        ${subs.map((sub) => `
          <div class="tb-row ${sub.status === 'done' ? 'done' : ''}" data-tid="${sub.id}">
            <button class="tb-play" data-play="${sub.id}">\u25B6</button>
            <span class="tb-label">${esc(sub.title)}</span>
            <span class="tb-time">${fmtDur(sub.time_spent_min || 0)}</span>
          </div>`).join('')}
      </div>` : '';

    const { ov, close } = modal(`
      <div class="sw-modal">
        <div class="sw-head">
          <div class="sw-crumb">${crumb}</div>
          <button class="sw-x" id="sw-close" title="close">\u2715</button>
        </div>
        <div class="sw-title-row">
          <button class="sw-icon" id="sw-expand" title="open full view">\u2197</button>
          <h2 class="sw-title">${esc(t.title || 'task')}</h2>
          <button class="sw-icon sw-flag ${t.priority_flag ? 'on' : ''}" id="sw-flag" title="flag priority">\u2691</button>
        </div>
        <div class="sw-meta">
          <div class="sw-meta-cell"><label>Start</label><span class="sw-pill">${startTxt}</span></div>
          <div class="sw-meta-cell right"><label>Time planned</label><span class="sw-pill">${plannedTxt}</span></div>
        </div>
        <textarea id="t-will" class="sw-will" rows="2" placeholder="I will work on\u2026"></textarea>
        <div class="sw-row">
          <div class="sw">
            <button class="sw-play" id="t-toggle" title="start">\u25B6</button>
            <div class="sw-read t-read" id="t-read" data-tid="${t.id}">00:00:00</div>
            <button class="sw-ic" id="t-reset" title="reset">\u21BB</button>
            <button class="sw-ic sw-check" id="t-stop" title="stop & log">\u2713</button>
          </div>
          <div class="sw-extra">
            ${block ? '<button class="sw-icon" id="sw-dup" title="duplicate block">\u29C9</button>' : ''}
            ${block ? '<button class="sw-icon" id="sw-rmblock" title="remove from calendar">\u2715</button>' : ''}
          </div>
        </div>
        <div class="t-active-label muted small" id="t-active-label"></div>
        <div class="sw-manual">
          <span class="muted small">or log</span>
          <input id="t-mins" type="text" inputmode="numeric" placeholder="min" />
          <button class="ghost" id="t-logman">add</button>
          ${block && !block.completed ? '<button class="ghost" id="sw-bdone">mark block studied</button>' : ''}
        </div>
        ${breakdown}
        <div class="sw-foot">
          <span class="muted">Done with the entire task?</span>
          ${t.status !== 'done'
            ? '<button class="primary" data-m="done">Mark Task Complete</button>'
            : '<span class="muted small">completed</span>'}
        </div>
      </div>`, async (act) => {
      if (act === 'done') {
        if (Timer.state.running && family.some((x) => x.id === Timer.state.task_id)) await Timer.stop();
        await Api.patch('/tasks/' + t.id, { status: 'done' }); await loadAll();
      }
    });

    const read = ov.querySelector('#t-read');
    const label = ov.querySelector('#t-active-label');
    const toggle = ov.querySelector('#t-toggle');

    const repaint = () => {
      const a = familyActive();
      if (a) {
        read.dataset.tid = a.id;
        read.textContent = Timer.fmt(Timer.elapsedSec());
        label.textContent = (a.id === t.id ? 'timing this task' : 'timing: ' + a.title) + (Timer.paused ? ' (paused)' : '');
        toggle.textContent = Timer.paused ? '\u25B6' : '\u23F8';
        toggle.classList.toggle('on', !Timer.paused);
      } else {
        read.dataset.tid = t.id;
        read.textContent = '00:00:00';
        label.textContent = '';
        toggle.textContent = '\u25B6';
        toggle.classList.remove('on');
      }
      ov.querySelectorAll('.tb-row').forEach((r) => {
        const on = a && +r.dataset.tid === a.id;
        r.classList.toggle('active', !!on);
        const pb = r.querySelector('.tb-play');
        if (pb) pb.textContent = on ? (Timer.paused ? '\u25B6' : '\u23F8') : '\u25B6';
      });
    };
    repaint();

    const startOn = async (id, title) => { const ok = await Timer.start(id, title); if (ok) repaint(); return ok; };

    toggle.onclick = async () => {
      const a = familyActive();
      if (a) {
        if (Timer.paused) { await Timer.resume(); } else { await Timer.pause(); }
        repaint(); return;
      }
      if (!hasSubs) {
        const will = (ov.querySelector('#t-will')?.value || '').trim();
        if (will) {
          const choice = await chooseParentOrSub(ov, will);
          if (choice === 'cancel') return;
          if (choice === 'sub') {
            const created = await Api.post('/tasks', {
              title: will, parent_id: t.id, time_needed_min: 30, course_id: t.course_id || null,
            });
            await startOn(created.id, created.title);
            await loadAll();
            const fresh = S.tasks.find((x) => x.id === t.id);
            close(); if (fresh) timerModal(fresh);
            return;
          }
        }
      }
      await startOn(t.id, t.title);
    };

    ov.querySelector('#t-reset').onclick = async () => {
      if (familyActive()) { await Timer.cancel(); repaint(); toast('session reset'); }
    };
    ov.querySelector('#t-stop').onclick = async () => { await Timer.stop(); close(); };
    ov.querySelector('#t-logman').onclick = async () => {
      const m = parseInt(ov.querySelector('#t-mins').value || '0', 10) || 0;
      if (m > 0) { await Api.post(`/tasks/${t.id}/log?minutes=${m}`); await loadAll(); close(); toast(`logged ${m} min`); }
    };

    // header affordances
    ov.querySelector('#sw-close').onclick = () => close();
    ov.querySelector('#sw-expand').onclick = () => { close(); taskModal(t); };
    const flag = ov.querySelector('#sw-flag');
    flag.onclick = async () => {
      const nv = !t.priority_flag;
      await Api.patch('/tasks/' + t.id, { priority_flag: nv });
      t.priority_flag = nv; flag.classList.toggle('on', nv);
      const live = S.tasks.find((x) => x.id === t.id); if (live) live.priority_flag = nv;
      loadAll();
    };

    // block icons
    const dup = ov.querySelector('#sw-dup');
    if (dup) dup.onclick = async () => {
      const dur = Math.round((new Date(block.end_at) - new Date(block.start_at)) / 60000) || need || 60;
      const ns = new Date(new Date(block.end_at).getTime());          // next slot, right after this one
      const ne = new Date(ns.getTime() + dur * 60000);
      const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
      await Api.post('/planned', { task_id: t.id, start_at: iso(ns), end_at: iso(ne) });
      await loadAll(); toast('block duplicated');
    };
    const rmb = ov.querySelector('#sw-rmblock');
    if (rmb) rmb.onclick = async () => { await Api.del('/planned/' + block.id); await loadAll(); close(); toast('block removed'); };
    const bdone = ov.querySelector('#sw-bdone');
    if (bdone) bdone.onclick = async () => { await Api.patch('/planned/' + block.id, { completed: true }); await loadAll(); close(); toast('block studied'); };

    // per-row play in the breakdown
    ov.querySelectorAll('.tb-play').forEach((pb) => {
      pb.onclick = async (e) => {
        e.stopPropagation();
        const id = +pb.dataset.play;
        const a = familyActive();
        if (a && a.id === id) {
          if (Timer.paused) { await Timer.resume(); } else { await Timer.pause(); }
          repaint();
        } else {
          const row = family.find((x) => x.id === id) || { id, title: 'task' };
          await startOn(id, row.title);
        }
      };
    });
  }

  // Inline two-way choice inside the stopwatch: time the parent task, or spin
  // the typed "I'll work on" text into a new subtask and time that. Resolves to
  // 'parent' | 'sub' | 'cancel'.
  function chooseParentOrSub(ov, will) {
    return new Promise((resolve) => {
      ov.querySelector('.t-choose')?.remove();
      const box = document.createElement('div');
      box.className = 't-choose';
      box.innerHTML = `
        <p class="muted small">log this time against\u2026</p>
        <div class="t-choose-btns">
          <button class="ghost" data-c="parent">the whole task</button>
          <button class="primary" data-c="sub">a new subtask \u201c${esc(will)}\u201d</button>
        </div>
        <button class="link-btn" data-c="cancel">cancel</button>`;
      ov.querySelector('.timer').appendChild(box);
      box.querySelectorAll('[data-c]').forEach((b) => {
        b.onclick = () => { box.remove(); resolve(b.dataset.c); };
      });
    });
  }

  // ---------- panel handlers ----------
  async function onTaskAction(act, tid) {
    const t = S.tasks.find((x) => x.id === tid);
    try {
      if (act === 'done') await Api.patch('/tasks/' + tid, { status: 'done' });
      if (act === 'flag') await Api.patch('/tasks/' + tid, { priority_flag: !t.priority_flag });
      if (act === 'del' && confirm('Delete task?')) await Api.del('/tasks/' + tid);
      if (act === 'edit') return taskModal(t);
      await loadAll();
    } catch (e) { toast(e.message, true); }
  }

  // ---------- modals ----------
  function modal(html, onAction) {
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


  function swatchHtml(sel) {
    return `<div class="swatches">${PALETTE.map((c) =>
      `<div class="swatch ${c === sel ? 'sel' : ''}" data-c="${c}"
            style="background:${c}"></div>`).join('')}</div>`;
  }
  function wireSwatches(ov) {
    for (const s of ov.querySelectorAll('.swatch'))
      s.onclick = () => { ov.querySelector('.swatch.sel')?.classList.remove('sel');
                          s.classList.add('sel'); };
  }

  function taskModal(t) {
    const isNew = !t;
    const subs = (t?.subtasks || []);
    const rolled = subs.length > 0;
    const parentTask = t?.parent_id ? S.tasks.find((x) => x.id === t.parent_id) : null;
    const dueTz = t?.due_tz || S.settings.school_tz || 'America/New_York';

    // shared edit fields (course/category/due/tz/time-needed) — same IDs as before
    const fields = `
      <div class="frow">
        <div><label>course</label><select id="m-course">
          <option value="">\u2014</option>
          ${S.courses.map((c) => `<option value="${c.id}" ${t?.course_id === c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}
        </select></div>
        <div><label>category</label><select id="m-cat">
          ${CATEGORIES.map((c) => `<option ${t?.category === c ? 'selected' : ''}>${c}</option>`).join('')}
        </select></div>
      </div>
      <div class="frow">
        <div><label>due date</label><input id="m-due-d" type="date" /></div>
        <div><label>due time</label><input id="m-due-t" type="time" value="23:59" /></div>
        <div><label>timezone</label>
          <div class="tz-pick"><select id="m-tz-country"></select><select id="m-tz-zone"></select></div></div>
        <div><label>time needed${rolled ? ' (from subtasks)' : ''}</label>
          <div class="dur ${rolled ? 'disabled' : ''}" id="m-need" data-min="${t?.time_needed_min ?? 60}">
            <div class="dseg">
              <button type="button" class="dstep" data-k="h" data-d="1" ${rolled ? 'disabled' : ''}>\u25B2</button>
              <input class="dh" type="text" inputmode="numeric" maxlength="2" ${rolled ? 'disabled' : ''}
                value="${Math.floor((t?.time_needed_min ?? 60) / 60)}" /><i>h</i>
              <button type="button" class="dstep" data-k="h" data-d="-1" ${rolled ? 'disabled' : ''}>\u25BC</button>
            </div>
            <div class="dseg">
              <button type="button" class="dstep" data-k="m" data-d="1" ${rolled ? 'disabled' : ''}>\u25B2</button>
              <input class="dm" type="text" inputmode="numeric" maxlength="2" ${rolled ? 'disabled' : ''}
                value="${String((t?.time_needed_min ?? 60) % 60).padStart(2, '0')}" /><i>m</i>
              <button type="button" class="dstep" data-k="m" data-d="-1" ${rolled ? 'disabled' : ''}>\u25BC</button>
            </div>
          </div></div>
      </div>`;

    const saveHandler = async (act, ovEl) => {
      if (act === 'trash' || act === 'done') return;   // handled manually below
      if (act !== 'save') return;
      const dd = ovEl.querySelector('#m-due-d').value;
      const body = {
        title: ovEl.querySelector('#m-title').value.trim() || 'untitled',
        course_id: +ovEl.querySelector('#m-course').value || null,
        category: ovEl.querySelector('#m-cat').value,
        notes: ovEl.querySelector('#m-notes').value,
        due_at: dd ? `${dd}T${ovEl.querySelector('#m-due-t').value || '23:59'}:00` : null,
        due_tz: ovEl.querySelector('#m-tz-zone')?.value || (S.settings.school_tz || 'America/New_York'),
      };
      if (!rolled) body.time_needed_min = +ovEl.querySelector('#m-need').dataset.min || 60;
      t ? await Api.patch('/tasks/' + t.id, body) : await Api.post('/tasks', body);
      await loadAll();
      toast(t ? `updated \u00b7 ${body.title}` : `added task \u00b7 ${body.title}`);
    };

    // ---- NEW TASK: simple create form ----
    if (isNew) {
      const { ov } = modal(`
        <h2>new task</h2>
        <div class="frow"><label>title</label>
          <input id="m-title" value="" placeholder="Homework 4\u2026" /></div>
        ${fields}
        <div class="frow col"><label>notes</label>
          <textarea id="m-notes" rows="3" placeholder="details, links, instructions\u2026"></textarea></div>
        <p class="muted small">save the task first to add subtasks.</p>
        ${ACTIONS('save')}`, saveHandler);
      initTzPicker(ov, dueTz);
      if (!rolled) wireStepper(ov.querySelector('#m-need'));
      ov.querySelector('#m-title').focus();
      return;
    }

    // ---- EDIT: runway command center ----
    const courseName = t.course_id ? (S.courses.find((c) => c.id === t.course_id)?.name || '') : '';
    const dueChip = t.due_at
      ? Api.fmtInZone(t.due_at, dueTz, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true })
          .replace(' PM', 'pm').replace(' AM', 'am')
      : 'no due date';

    const { ov, close } = modal(`
      <div class="rw">
        <div class="rw-top">
          <input id="m-title" class="rw-title" value="${esc(t.title || '')}" />
          <button class="ic ${t.priority_flag ? 'on' : ''}" id="rw-flag" title="flag priority">\u2691</button>
          <button class="ic" id="rw-complete" title="${t.status === 'done' ? 'completed' : 'mark complete'}">\u2713</button>
        </div>
        ${parentTask ? `<p class="muted small parentof">\u21B3 part of <strong>${esc(parentTask.title)}</strong></p>` : ''}
        <div class="rw-chips">
          <span class="chip crs" id="rw-course"><i>\u25C9</i> ${courseName ? esc(courseName) : 'no course'}</span>
          <span class="chip" id="rw-cat">${esc(t.category || '\u2014')}</span>
          <span class="chip" id="rw-due">${dueChip}</span>
          <button class="chip edit" id="rw-edit-toggle">edit details</button>
        </div>

        <div class="rw-card" id="rw-runway"></div>

        <div class="rw-work">
          <div class="rw-sw">
            <div class="t-read" id="t-read" data-tid="${t.id}">00:00:00</div>
            <button class="play" id="t-toggle" title="start">\u25B6</button>
            <div class="muted small" id="t-active-label"></div>
          </div>
          <div class="rw-subs">
            <div class="sub-head"><label>subtasks</label><span class="muted small" id="m-sub-roll"></span></div>
            <div id="m-sub-list"></div>
            <div class="sub-add">
              <input id="m-sub-new" placeholder="add a subtask and press enter" />
              <div class="dur sm" id="m-sub-dur" data-min="30">
                <input class="dh" type="text" maxlength="2" value="0" /><i>h</i>
                <input class="dm" type="text" maxlength="2" value="30" /><i>m</i>
              </div>
            </div>
          </div>
        </div>

        <div class="rw-fold" id="rw-details" hidden>${fields}</div>
        <div class="rw-foldhead" id="rw-notes-toggle"><i>\u270E</i> notes</div>
        <textarea id="m-notes" class="rw-notes" rows="3" hidden
          placeholder="details, links, instructions\u2026">${esc(t.notes || '')}</textarea>

        <div class="actions rw-foot">
          <button class="ghost danger-btn" id="rw-trash">move to trash</button>
          <span class="spacer"></span>
          <button class="ghost" data-m="cancel">cancel</button>
          <button class="primary" data-m="save">save</button>
        </div>
      </div>`, saveHandler);

    // prefill due + tz + stepper (existing behaviour)
    if (t.due_at) {
      ov.querySelector('#m-due-d').value = Api.dayInZone(t.due_at, dueTz);
      ov.querySelector('#m-due-t').value = Api.fmtInZone(t.due_at, dueTz, { hour: '2-digit', minute: '2-digit', hour12: false });
    }
    initTzPicker(ov, dueTz);
    if (!rolled) wireStepper(ov.querySelector('#m-need'));

    // work-zone stopwatch follows whichever family member is timing
    const family = [t, ...subs];
    const familyActive = () => (Timer.state.running ? family.find((x) => x.id === Timer.state.task_id) : null);
    const read = ov.querySelector('#t-read');
    const label = ov.querySelector('#t-active-label');
    const toggle = ov.querySelector('#t-toggle');
    const repaintWork = () => {
      const a = familyActive();
      if (a) {
        read.dataset.tid = a.id;
        read.textContent = Timer.fmt(Timer.elapsedSec());
        label.textContent = (a.id === t.id ? 'timing this task' : 'timing: ' + a.title) + (Timer.paused ? ' (paused)' : '');
        toggle.textContent = Timer.paused ? '\u25B6' : '\u23F8';
        toggle.classList.toggle('on', !Timer.paused);
      } else {
        read.dataset.tid = t.id; read.textContent = '00:00:00';
        label.textContent = ''; toggle.textContent = '\u25B6'; toggle.classList.remove('on');
      }
    };
    toggle.onclick = async () => {
      const a = familyActive();
      if (a) { if (Timer.paused) { await Timer.resume(); } else { await Timer.pause(); } }
      else { await Timer.start(t.id, t.title); }
      repaintWork();
    };

    wireSubtasks(ov, t, { showTimeBar: false, onChange: repaintWork });
    repaintWork();
    renderRunway();

    function renderRunway() {
      const el = ov.querySelector('#rw-runway');
      if (!t.due_at) { el.innerHTML = '<div class="rw-empty">no due date \u2014 add one to see your runway</div>'; return; }
      const cu = S.cushionByTask[t.id];
      const due = new Date(t.due_at);
      const now = new Date();
      let startD = t.start_date ? new Date(t.start_date + 'T00:00:00') : new Date(t.created_at || now);
      if (!(startD < due)) startD = new Date(now.getTime() - 86400000);
      const span = Math.max(1, due - startD);
      const fr = (d) => Math.max(0, Math.min(1, (new Date(d) - startD) / span));
      const nowPct = +(fr(now) * 100).toFixed(1);
      const daysLeft = Math.ceil((due - now) / 86400000);
      const fam = new Set([t.id, ...subs.map((x) => x.id)]);
      const ticks = (S.planned || []).filter((b) => fam.has(b.task_id)).map((b) => +(fr(b.start_at) * 100).toFixed(1));
      let lvl = cu ? cu.level : 'green';
      let cushTxt;
      if (cu) { const m = cu.cushion_min; cushTxt = m >= 0 ? `${fmtDur(m)} cushion` : `${fmtDur(-m)} short`; }
      else { cushTxt = 'on track'; }
      const need = t.time_needed_min || 0, spent = t.time_spent_min || 0;
      const pct = need ? Math.min(100, Math.round(spent / need * 100)) : 0;
      const stillNeed = Math.max(0, need - spent);
      el.innerHTML = `
        <div class="rw-rl"><span>RUNWAY TO DEADLINE</span><span class="rw-cush ${lvl}">${cushTxt}</span></div>
        <div class="rw-track">
          <div class="rw-base"></div>
          <div class="rw-elapsed" style="width:${nowPct}%"></div>
          <div class="rw-slack ${lvl}" style="left:${nowPct}%"></div>
          ${ticks.map((f) => `<div class="rw-tick" style="left:${f}%"></div>`).join('')}
          <div class="rw-now" style="left:${nowPct}%"></div>
        </div>
        <div class="rw-axis"><span>now</span><span>${daysLeft >= 0 ? daysLeft + 'd to due' : 'overdue'}</span></div>
        <div class="rw-bar"><div class="rw-fill" style="width:${pct}%"></div></div>
        <div class="rw-barlab"><span>TIME USED <b>${fmtDur(spent)}</b></span><span>of ${fmtDur(need)}</span><span>STILL NEED <b>${fmtDur(stillNeed)}</b></span></div>`;
    }

    // chips / disclosures
    const detailsEl = ov.querySelector('#rw-details');
    const showDetails = () => { detailsEl.hidden = !detailsEl.hidden; };
    ov.querySelector('#rw-edit-toggle').onclick = showDetails;
    ov.querySelector('#rw-course').onclick = showDetails;
    ov.querySelector('#rw-cat').onclick = showDetails;
    ov.querySelector('#rw-due').onclick = showDetails;
    const notesEl = ov.querySelector('#m-notes');
    ov.querySelector('#rw-notes-toggle').onclick = () => { notesEl.hidden = !notesEl.hidden; if (!notesEl.hidden) notesEl.focus(); };

    // flag / complete / trash
    const flag = ov.querySelector('#rw-flag');
    flag.onclick = async () => {
      const nv = !t.priority_flag;
      await Api.patch('/tasks/' + t.id, { priority_flag: nv });
      t.priority_flag = nv; flag.classList.toggle('on', nv);
      const live = S.tasks.find((x) => x.id === t.id); if (live) live.priority_flag = nv;
      loadAll();
    };
    ov.querySelector('#rw-complete').onclick = async () => {
      if (t.status === 'done') return;
      if (Timer.state.running && family.some((x) => x.id === Timer.state.task_id)) await Timer.stop();
      await Api.patch('/tasks/' + t.id, { status: 'done' }); await loadAll(); close();
    };
    ov.querySelector('#rw-trash').onclick = async () => {
      if (!confirm('Delete task?')) return;
      await Api.del('/tasks/' + t.id); await loadAll(); close();
    };
  }

  // Subtasks: render list, add (enter), toggle done, delete. Each has its own
  // time estimate; the parent's totals roll up server-side.
  function wireSubtasks(ov, parent, opts = {}) {
    const showBar = opts.showTimeBar !== false;
    const onChange = opts.onChange || (() => {});
    const listEl = ov.querySelector('#m-sub-list');
    const rollEl = ov.querySelector('#m-sub-roll');
    let subs = (parent.subtasks || []).slice();

    const markActive = () => {
      const cur = (window.__TIMER && window.__TIMER.running) ? window.__TIMER.task_id : null;
      listEl.querySelectorAll('[data-tid]').forEach((r) => {
        const on = cur && +r.dataset.tid === cur;
        r.classList.toggle('timing', !!on);
        const pb = r.querySelector('.tb-play'); if (pb) pb.textContent = on ? '\u23F8' : '\u25B6';
      });
    };

    const render = () => {
      const directMin = (parent.direct_spent_min != null)
        ? parent.direct_spent_min : (subs.length ? 0 : (parent.time_spent_min || 0));
      const need = subs.length ? subs.reduce((a, s) => a + s.time_needed_min, 0) : (parent.time_needed_min || 0);
      const usedSubs = subs.reduce((a, s) => a + (s.time_spent_min || 0), 0);
      const used = usedSubs + directMin;
      const done = subs.filter((s) => s.status === 'done').length;

      listEl.innerHTML = `
        ${showBar ? `<div class="time-used-bar">
          <span>TIME USED <strong>${fmtDur(used)}</strong></span>
          <span>STILL NEED <strong>${fmtDur(Math.max(0, need - used))}</strong></span>
        </div>` : ''}
        <div class="sub-row direct" data-tid="${parent.id}">
          <button type="button" class="tb-play" data-play="${parent.id}">\u25B6</button>
          <span class="sub-title">this task \u00b7 directly</span>
          <span class="muted small">${fmtDur(directMin)}</span>
        </div>
        ${subs.map((s) => `
          <div class="sub-row ${s.status === 'done' ? 'done' : ''}" data-sid="${s.id}" data-tid="${s.id}">
            <input type="checkbox" ${s.status === 'done' ? 'checked' : ''} data-toggle />
            <button type="button" class="tb-play" data-play="${s.id}">\u25B6</button>
            <span class="sub-title">${esc(s.title)}</span>
            <span class="muted small">${fmtDur(s.time_spent_min || 0)} / ${fmtDur(s.time_needed_min)}</span>
            <button class="x" data-del>\u2715</button>
          </div>`).join('')}`;
      rollEl.textContent = subs.length ? `${done}/${subs.length} done` : '';

      for (const cb of listEl.querySelectorAll('[data-toggle]'))
        cb.onchange = async () => {
          const id = +cb.closest('[data-sid]').dataset.sid;
          await Api.patch('/tasks/' + id, { status: cb.checked ? 'done' : 'todo' });
          const s = subs.find((x) => x.id === id); if (s) s.status = cb.checked ? 'done' : 'todo';
          render(); onChange(); loadAll();
        };
      for (const x of listEl.querySelectorAll('[data-del]'))
        x.onclick = async () => {
          const id = +x.closest('[data-sid]').dataset.sid;
          await Api.del('/tasks/' + id);
          subs = subs.filter((s) => s.id !== id);
          render(); onChange(); loadAll();
        };
      for (const pb of listEl.querySelectorAll('.tb-play'))
        pb.onclick = async () => {
          const id = +pb.dataset.play;
          const cur = (window.__TIMER && window.__TIMER.running) ? window.__TIMER.task_id : null;
          if (cur === id) {
            if (window.__TIMER.paused) { await Timer.resume(); } else { await Timer.pause(); }
            markActive(); onChange(); return;
          }
          const row = (id === parent.id) ? parent : subs.find((x) => x.id === id);
          await Timer.start(id, row ? row.title : 'task');
          markActive(); onChange();
        };
      markActive();
    };

    const dur = ov.querySelector('#m-sub-dur');
    const durMin = () => (+dur.querySelector('.dh').value || 0) * 60 + (+dur.querySelector('.dm').value || 0);
    const newInp = ov.querySelector('#m-sub-new');
    newInp.onkeydown = async (e) => {
      if (e.key !== 'Enter' || !newInp.value.trim()) return;
      const created = await Api.post('/tasks', {
        title: newInp.value.trim(), parent_id: parent.id,
        time_needed_min: durMin() || 30, course_id: parent.course_id || null,
      });
      subs.push({ ...created, status: 'todo' });
      newInp.value = '';
      render(); onChange(); loadAll();
    };
    render();
  }

  async function initTzPicker(ov, selectedZone) {
    const cSel = ov.querySelector('#m-tz-country');
    const zSel = ov.querySelector('#m-tz-zone');
    if (!cSel || !zSel) return;
    const country = (S.settings.country || detectCountry() || 'US');
    let data;
    try { data = await Api.get('/config/timezones?country=' + country); }
    catch { data = { countries: ['US'], zones: [] }; }
    cSel.innerHTML = data.countries.map((c) => `<option value="${c}" ${c === country ? 'selected' : ''}>${c}</option>`).join('');
    const fillZones = async (cc) => {
      const d = await Api.get('/config/timezones?country=' + cc);
      zSel.innerHTML = d.zones.length
        ? d.zones.map((z) => `<option value="${z.id}" ${z.id === selectedZone ? 'selected' : ''}>${z.label}</option>`).join('')
        : `<option value="${selectedZone}">${selectedZone}</option>`;
    };
    await fillZones(country);
    cSel.onchange = () => fillZones(cSel.value);
  }

  function wireStepper(el) {
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
    // arrows: hours \u00b11, minutes \u00b15 with rollover
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

  function detectCountry() {
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
      if (tz.startsWith('America/')) return 'US';
      if (tz.startsWith('Asia/Kolkata')) return 'IN';
      if (tz.startsWith('Europe/London')) return 'GB';
      if (tz.startsWith('Australia/')) return 'AU';
    } catch { /* noop */ }
    return 'US';
  }

  function courseModal(course) {
    const sel = course?.color || PALETTE[S.courses.length % PALETTE.length];
    const m = modal(`
      <h2>${course ? 'edit course' : 'new course'}</h2>
      <div class="frow"><label>name</label><input id="m-name" value="${esc(course?.name || '')}" placeholder="CMPEN 331" /></div>
      <div class="frow"><label>instructor</label><input id="m-inst" value="${esc(course?.instructor || '')}" placeholder="Prof. Ada Lovelace" /></div>
      <div class="frow"><label>link</label><input id="m-url" value="${esc(course?.url || '')}" placeholder="course page or syllabus URL" /></div>
      <div class="frow"><label>credits</label><input id="m-cr" type="number" min="0" max="12" step="0.5" value="${course?.credits ?? ''}" placeholder="3" /></div>
      <div class="frow"><label>color</label>${swatchHtml(sel)}</div>
      <div class="frow"><label>notes</label><textarea id="m-notes" rows="3" placeholder="office hours, policies, reading sources…">${esc(course?.notes || '')}</textarea></div>
      ${course ? '<div class="actions left"><button class="ghost danger-btn" data-m="del">delete</button><button class="ghost" id="m-grades" type="button">grades…</button><button class="ghost" id="m-schedule" type="button">class times…</button></div>' : ''}
      ${ACTIONS(course ? 'save' : 'add')}`,
      async (act, ov) => {
        if (act === 'del') { await Api.del('/courses/' + course.id); await loadAll(); return toast('course deleted'); }
        if (act !== 'save') return;
        const nm = ov.querySelector('#m-name').value.trim() || 'course';
        const color = ov.querySelector('.swatch.sel')?.dataset.c || PALETTE[0];
        const crv = ov.querySelector('#m-cr').value.trim();
        const body = {
          name: nm, color,
          instructor: ov.querySelector('#m-inst').value.trim(),
          url: ov.querySelector('#m-url').value.trim(),
          notes: ov.querySelector('#m-notes').value,
          credits: crv === '' ? null : Number(crv),
        };
        if (course) await Api.patch('/courses/' + course.id, body);
        else await Api.post('/courses', body);
        await loadAll();
        toast(`${course ? 'updated' : 'added'} course \u00b7 ${nm}`);
      });
    const gb = m.ov.querySelector('#m-grades');
    if (gb) gb.onclick = () => gradesModal(course);
    const sb = m.ov.querySelector('#m-schedule');
    if (sb) sb.onclick = () => courseScheduleModal(course);
    wireSwatches($('modal-root'));
  }

  // ----- course class-time scheduling -----
  function courseClassGroups(course) {
    const groups = {};
    for (const a of S.activities.filter((x) => x.course_id === course.id)) {
      const k = `${a.title}|${a.start_min}|${a.end_min}|${a.color}`;
      (groups[k] ??= { ...a, ids: [], days: [] });
      groups[k].ids.push(a.id);
      groups[k].days.push(a.weekday);
    }
    return Object.values(groups).sort((a, b) => a.start_min - b.start_min);
  }

  function courseScheduleModal(course) {
    const ABBR = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const fmt12 = (m) => { const h = Math.floor(m / 60); return `${((h + 11) % 12) + 1}:${pad(m % 60)} ${h < 12 ? 'AM' : 'PM'}`; };
    const groups = courseClassGroups(course);
    const rows = groups.map((g) => `
      <div class="side-item clickable" data-gk="${g.ids.join(',')}">
        <span class="dot" style="background:${g.color}"></span>
        <span class="side-txt">
          <span class="nm">${esc(g.title)}</span>
          <span class="meta">${g.days.slice().sort((a, b) => a - b).map((d) => ABBR[d]).join(' · ')} · ${fmt12(g.start_min)}–${fmt12(g.end_min)}</span>
        </span>
      </div>`).join('') || '<p class="muted small">no class times scheduled yet — add one below.</p>';
    const { ov } = modal(`
      <h2>class times · ${esc(course.name)}</h2>
      <p class="muted small" style="margin:-8px 0 12px">These show up on your calendar every week, colored like this course.</p>
      <div id="cs-list">${rows}</div>
      <div class="actions"><span class="spacer"></span>
        <button class="ghost" data-m="cancel">close</button>
        <button class="primary" id="cs-add" type="button">+ add class time</button></div>`);
    // activityModal's own overlay auto-closes itself right after onDone runs
    // (see modal()'s finally{close()}), so reopen on the next tick — reopening
    // synchronously here would get wiped out by that trailing close().
    const reopen = () => setTimeout(() => courseScheduleModal(course), 0);
    for (const row of ov.querySelectorAll('[data-gk]')) {
      row.onclick = () => {
        const g = groups.find((x) => x.ids.join(',') === row.dataset.gk);
        activityModal(g, { courseCtx: course, onDone: reopen });
      };
    }
    ov.querySelector('#cs-add').onclick = () => {
      activityModal(null, { courseCtx: course, onDone: reopen });
    };
  }

  // ----- grades -----
  function gradeLetter(p) {
    if (p === null || p === undefined) return '';
    for (const [f, l] of [[93, 'A'], [90, 'A-'], [87, 'B+'], [83, 'B'], [80, 'B-'],
      [77, 'C+'], [73, 'C'], [70, 'C-'], [67, 'D+'], [60, 'D'], [0, 'F']]) if (p >= f) return l;
    return 'F';
  }
  function gradeCalc(cats) {
    const graded = [];
    for (const c of cats) {
      const its = (c.items || []).filter((i) => (+i.possible || 0) > 0);
      const e = its.reduce((a, i) => a + (+i.earned || 0), 0);
      const p = its.reduce((a, i) => a + (+i.possible || 0), 0);
      if (p > 0 && (+c.weight || 0) > 0) graded.push({ w: +c.weight, pct: e / p * 100 });
    }
    const ws = graded.reduce((a, b) => a + b.w, 0);
    const overall = ws > 0 ? graded.reduce((a, b) => a + b.pct * b.w, 0) / ws : null;
    return { percent: overall === null ? null : Math.round(overall * 10) / 10, letter: gradeLetter(overall) };
  }

  async function gradesModal(course) {
    let data; try { data = await Api.get('/grades/' + course.id); } catch (e) { data = { categories: [] }; }
    const state = (data.categories || []).map((c) => ({
      name: c.name, weight: c.weight,
      items: (c.items || []).map((i) => ({ title: i.title, earned: i.earned, possible: i.possible })),
    }));
    if (!state.length) state.push({ name: '', weight: 0, items: [] });

    const { ov, close } = modal(`<h2>grades \u00b7 ${esc(course.name)}</h2>
      <div class="gr-summary" id="gr-sum"></div>
      <div id="gr-body"></div>
      <button class="ghost" id="gr-addcat" type="button" style="margin-top:10px">+ category</button>
      <p class="muted small" style="margin-top:8px">Weights are normalized across categories that have grades, so empty ones don\u2019t count yet.</p>
      <div class="actions"><span class="spacer"></span>
        <button class="ghost" data-m="cancel">cancel</button>
        <button class="primary" id="gr-save" type="button">save</button></div>`);

    const paintSum = () => {
      const s = gradeCalc(state);
      ov.querySelector('#gr-sum').innerHTML = s.percent === null
        ? '<span class="gr-none">no grades entered yet</span>'
        : `<span class="gr-letter">${s.letter}</span><span class="gr-pct">${s.percent}%</span>`;
    };
    const render = () => {
      ov.querySelector('#gr-body').innerHTML = state.map((c, ci) => `
        <div class="gr-cat">
          <div class="gr-cat-head">
            <input class="gr-cname" data-ci="${ci}" value="${esc(c.name)}" placeholder="category (e.g. Homework)" />
            <input class="gr-cweight" data-ci="${ci}" type="number" min="0" max="100" value="${c.weight || ''}" placeholder="wt" /><span class="gr-wpct">%</span>
            <button class="gr-x gr-del-cat" data-ci="${ci}" type="button" title="remove category">\u2715</button>
          </div>
          <div class="gr-items">
            ${(c.items || []).map((it, ii) => `<div class="gr-item">
              <input class="gr-title" data-ci="${ci}" data-ii="${ii}" value="${esc(it.title)}" placeholder="item" />
              <input class="gr-earned" data-ci="${ci}" data-ii="${ii}" type="number" step="0.1" value="${it.earned || ''}" placeholder="got" />
              <span class="gr-sl">/</span>
              <input class="gr-possible" data-ci="${ci}" data-ii="${ii}" type="number" step="0.1" value="${it.possible || ''}" placeholder="max" />
              <button class="gr-x gr-del-item" data-ci="${ci}" data-ii="${ii}" type="button" title="remove">\u2715</button>
            </div>`).join('')}
            <button class="gr-additem" data-ci="${ci}" type="button">+ item</button>
          </div>
        </div>`).join('');

      ov.querySelectorAll('.gr-cname').forEach((el) => { el.oninput = () => { state[+el.dataset.ci].name = el.value; }; });
      ov.querySelectorAll('.gr-cweight').forEach((el) => { el.oninput = () => { state[+el.dataset.ci].weight = +el.value || 0; paintSum(); }; });
      ov.querySelectorAll('.gr-title').forEach((el) => { el.oninput = () => { state[+el.dataset.ci].items[+el.dataset.ii].title = el.value; }; });
      ov.querySelectorAll('.gr-earned').forEach((el) => { el.oninput = () => { state[+el.dataset.ci].items[+el.dataset.ii].earned = +el.value || 0; paintSum(); }; });
      ov.querySelectorAll('.gr-possible').forEach((el) => { el.oninput = () => { state[+el.dataset.ci].items[+el.dataset.ii].possible = +el.value || 0; paintSum(); }; });
      ov.querySelectorAll('.gr-additem').forEach((el) => { el.onclick = () => { state[+el.dataset.ci].items.push({ title: '', earned: 0, possible: 0 }); render(); }; });
      ov.querySelectorAll('.gr-del-item').forEach((el) => { el.onclick = () => { state[+el.dataset.ci].items.splice(+el.dataset.ii, 1); render(); }; });
      ov.querySelectorAll('.gr-del-cat').forEach((el) => { el.onclick = () => { state.splice(+el.dataset.ci, 1); if (!state.length) state.push({ name: '', weight: 0, items: [] }); render(); }; });
      paintSum();
    };
    ov.querySelector('#gr-addcat').onclick = () => { state.push({ name: '', weight: 0, items: [] }); render(); };
    ov.querySelector('#gr-save').onclick = async () => {
      try {
        await Api.put('/grades/' + course.id, { categories: state });
        toast('grades saved'); close();
        if ($('learn') && !$('learn').classList.contains('hidden')) renderHiveCourses();
      } catch (e) { toast('save failed'); }
    };
    render();
  }

  function activityModal(existing, opts) {
    const { courseCtx, onDone } = opts || {};
    const initDays = new Set(existing?.days || []);
    const PRESETS = [
      { key: 'class',   label: 'Class',   title: 'Class',   color: '#56646E', s: '10:00', e: '10:50', days: [] },
      { key: 'lunch',   label: 'Lunch',   title: 'Lunch',   color: '#B59B5B', s: '12:00', e: '13:00', days: [0, 1, 2, 3, 4] },
      { key: 'workout', label: 'Workout', title: 'Workout', color: '#5F6B5A', s: '17:00', e: '18:00', days: [0, 2, 4] },
      { key: 'dinner',  label: 'Dinner',  title: 'Dinner',  color: '#7A5A4A', s: '18:30', e: '19:30', days: [0, 1, 2, 3, 4, 5, 6] },
    ];
    const initColor = existing?.color || courseCtx?.color || '#5F6B5A';
    const heading = courseCtx
      ? `${existing ? 'edit' : 'new'} class time · ${esc(courseCtx.name)}`
      : `${existing ? 'edit activity' : 'new activity'}`;
    const { ov } = modal(`
      <h2>${heading}</h2>
      ${existing || courseCtx ? '' : `<div class="frow"><label>start from a preset</label>
        <div class="apresets">${PRESETS.map((p) => `<button type="button" class="apz" data-p="${p.key}">${p.label}</button>`).join('')}<button type="button" class="apz" data-p="custom">Custom</button></div></div>`}
      <div class="frow"><label>title</label><input id="m-name" value="${esc(existing?.title || '')}" placeholder="${courseCtx ? 'Lecture, Lab, Discussion…' : 'CMPEN 331 lecture / lunch / workout'}" /></div>
      <div class="frow"><label>days</label>
        <div class="daypick">${DAYS.map((d, i) => `<button data-d="${i}" class="${initDays.has(i) ? 'sel' : ''}">${d}</button>`).join('')}</div></div>
      <div class="frow">
        <div><label>start</label><input id="m-s" type="time" value="${existing ? minToHM(existing.start_min) : nowHM()}" /></div>
        <div><label>end</label><input id="m-e" type="time" value="${existing ? minToHM(existing.end_min) : plusHM(50)}" /></div>
      </div>
      <div class="frow"><label>color</label>${swatchHtml(initColor)}</div>
      <div class="apreview"><div class="apl">PREVIEW · how it lands on your week</div><div class="achip" id="achip"></div></div>
      ${existing ? '<div class="actions left"><button class="ghost danger-btn" data-m="del">delete</button></div>' : ''}
      ${ACTIONS(existing ? 'save' : (courseCtx ? 'add class time' : 'block it'))}`,
      async (act, ovEl) => {
        if (act === 'del') {
          await Promise.all((existing.ids).map((id) => Api.del('/activities/' + id)));
          await loadAll();
          if (onDone) return onDone();
          return toast('activity deleted');
        }
        if (act !== 'save') return;
        const days = [...ovEl.querySelectorAll('.daypick button.sel')].map((b) => +b.dataset.d);
        const s = hmToMin(ovEl.querySelector('#m-s').value);
        const e = hmToMin(ovEl.querySelector('#m-e').value);
        if (!days.length || e <= s) return toast('pick days and a valid time range', true);
        const title = ovEl.querySelector('#m-name').value.trim() || (courseCtx ? courseCtx.name : 'activity');
        const color = ovEl.querySelector('.swatch.sel')?.dataset.c || '#5F6B5A';
        const courseId = courseCtx?.id ?? existing?.course_id ?? null;
        // Update in place where a day is kept (same id, atomic PATCH — no
        // delete+recreate churn, and no window for a duplicate if this
        // ever fires twice), only delete days that were unchecked, only
        // create days that are newly checked.
        if (existing) {
          const idByDay = new Map(existing.days.map((d, i) => [d, existing.ids[i]]));
          const keep = new Set(days);
          await Promise.all(existing.days.filter((d) => !keep.has(d)).map((d) => Api.del('/activities/' + idByDay.get(d))));
          await Promise.all(days.map((d) => idByDay.has(d)
            ? Api.patch('/activities/' + idByDay.get(d), { title, color, start_min: s, end_min: e, course_id: courseId })
            : Api.post('/activities', { title, color, weekday: d, start_min: s, end_min: e, course_id: courseId })));
        } else {
          await Promise.all(days.map((d) => Api.post('/activities', { title, color, weekday: d, start_min: s, end_min: e, course_id: courseId })));
        }
        await loadAll();
        if (onDone) return onDone();
        toast(`${existing ? 'updated' : 'blocked'} \u00b7 ${title}`);
      });

    const ABBR = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const fmt12 = (hm) => {
      if (!hm) return '—';
      const [h, m] = hm.split(':').map(Number);
      return `${((h + 11) % 12) + 1}:${pad(m)} ${h < 12 ? 'AM' : 'PM'}`;
    };
    const chip = ov.querySelector('#achip');
    const updatePreview = () => {
      const title = ov.querySelector('#m-name').value.trim() || 'activity';
      const sel = [...ov.querySelectorAll('.daypick button.sel')].map((b) => +b.dataset.d).sort((a, b) => a - b);
      const dtxt = sel.length ? sel.map((d) => ABBR[d]).join(' · ') : 'pick days';
      const color = ov.querySelector('.swatch.sel')?.dataset.c || '#5F6B5A';
      chip.style.borderLeftColor = color;
      chip.style.background = color + '22';
      chip.innerHTML = `<b>${esc(title)}</b><span>${dtxt} \u00b7 ${fmt12(ov.querySelector('#m-s').value)}\u2013${fmt12(ov.querySelector('#m-e').value)}</span>`;
    };

    wireSwatches(ov);
    for (const sw of ov.querySelectorAll('.swatch')) sw.addEventListener('click', updatePreview);
    for (const b of ov.querySelectorAll('.daypick button'))
      b.onclick = () => { b.classList.toggle('sel'); updatePreview(); };
    for (const id of ['m-name', 'm-s', 'm-e']) ov.querySelector('#' + id).addEventListener('input', updatePreview);

    for (const z of ov.querySelectorAll('.apz')) z.onclick = () => {
      ov.querySelectorAll('.apz').forEach((x) => x.classList.toggle('on', x === z));
      const p = PRESETS.find((x) => x.key === z.dataset.p);
      if (!p) { ov.querySelector('#m-name').value = ''; ov.querySelector('#m-name').focus(); updatePreview(); return; }
      ov.querySelector('#m-name').value = p.title;
      ov.querySelector('#m-s').value = p.s; ov.querySelector('#m-e').value = p.e;
      ov.querySelectorAll('.daypick button').forEach((b) => b.classList.toggle('sel', p.days.includes(+b.dataset.d)));
      ov.querySelectorAll('.swatch').forEach((sw) => sw.classList.toggle('sel', sw.dataset.c === p.color));
      updatePreview();
    };

    updatePreview();
  }

  // ============================================================
  //  ANALYTICS  (insights page — Past view; Future is next pass)
  // ============================================================
  let anRange = 'this_week';
  let anMode = 'past';

  function downloadText(filename, text, mime) {
    const blob = new Blob([text], { type: mime || 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }
  const AN_RANGES = [
    ['today', 'Today'], ['yesterday', 'Yesterday'], ['this_week', 'This week'],
    ['last_week', 'Last week'], ['last_7', 'Last 7 days'], ['last_30', 'Last 30 days'],
    ['this_month', 'This month'], ['last_month', 'Last month'], ['all', 'All time'],
  ];

  function showView(name, btn, tab) {
    // Match by view name, not element identity, so the rail and the mobile
    // bottom nav (two separate elements per view) both reflect the active view.
    for (const b of document.querySelectorAll('[data-view]')) b.classList.toggle('active', b.dataset.view === name);
    const insights = name === 'insights';
    const learn = name === 'learn';
    const home = !insights && !learn;
    $('analytics').classList.toggle('hidden', !insights);
    const lv = $('learn'); if (lv) lv.classList.toggle('hidden', !learn);
    $('calendar').classList.toggle('hidden', !home);
    const bar = document.querySelector('.topbar'); if (bar) bar.classList.toggle('hidden', !home);
    const panel = $('panel'); if (panel) panel.classList.toggle('hidden', !home);
    // Courses collapses the right sidebar to reclaim its width (see learn.js
    // activateCourseWorkspace); mirror that here so Insights does too.
    if (insights && !document.body.classList.contains('no-right')) {
      document.body.classList.add('no-right');
      const rightToggle = document.getElementById('collapse-right');
      if (rightToggle) rightToggle.textContent = '‹';
      window.dispatchEvent(new Event('resize'));
    }
    if (insights) renderAnalytics(tab);
    if (learn) renderHiveCourses();
  }

  function renderHiveCourses() {
    const el = $('learn');
    if (!el || !window.HiveCourses) return;
    window.HiveCourses.render(el, S, Api);
  }

  let anTab = 'analytics';
  function renderAnalytics(initialTab) {
    if (initialTab) anTab = initialTab;
    const el = $('analytics');
    el.innerHTML = `
      <div class="an-tabs">
        <span class="an-tab" data-tab="analytics">Analytics</span>
        <span class="an-tab" data-tab="streak">Streak</span>
        <span class="an-tab" data-tab="cushion">Cushion</span>
        <span class="an-tab" data-tab="timeline">Timeline</span>
      </div>
      <div class="an-controls">
        <div class="seg an-pf"><span class="on" data-pf="past">Past</span><span data-pf="future">Future</span></div>
        <select class="an-range">${AN_RANGES.map(([k, l]) => `<option value="${k}" ${k === anRange ? 'selected' : ''}>${l}</option>`).join('')}</select>
        <button class="an-export" id="an-export" title="export time logs as CSV">export</button>
      </div>
      <div class="an-body" id="an-body"><p class="muted small">loading\u2026</p></div>`;
    el.querySelector('.an-range').onchange = (e) => { anRange = e.target.value; if (anMode === 'future') loadFuture(); else loadPast(); };
    const ex = el.querySelector('#an-export');
    if (ex) ex.onclick = async () => {
      try {
        const r = await Api.get('/analytics/export?range=' + encodeURIComponent(anRange));
        downloadText(r.filename, r.csv);
        toast(`exported ${r.count} time-log rows`);
      } catch (e) { toast('export failed'); }
    };
    for (const sp of el.querySelectorAll('.an-pf span')) sp.onclick = () => {
      el.querySelectorAll('.an-pf span').forEach((x) => x.classList.toggle('on', x === sp));
      anMode = sp.dataset.pf; if (anMode === 'future') loadFuture(); else loadPast();
    };
    for (const t of el.querySelectorAll('.an-tab[data-tab]')) t.onclick = () => showAnTab(t.dataset.tab);
    showAnTab(anTab);
  }

  function showAnTab(name) {
    anTab = name;
    const el = $('analytics');
    el.querySelectorAll('.an-tab').forEach((t) => t.classList.toggle('on', t.dataset.tab === name));
    const controls = el.querySelector('.an-controls');
    if (name === 'streak') { controls.classList.add('hidden'); loadStreak(); }
    else if (name === 'cushion') { controls.classList.add('hidden'); loadCushion(); }
    else if (name === 'timeline') { controls.classList.add('hidden'); loadTimeline(); }
    else { controls.classList.remove('hidden'); if (anMode === 'future') loadFuture(); else loadPast(); }
  }

  async function loadPast() {
    const body = $('an-body'); if (!body) return;
    body.innerHTML = '<p class="muted small">loading\u2026</p>';
    let d;
    try { d = await Api.get('/analytics/past?range=' + encodeURIComponent(anRange)); }
    catch (e) { body.innerHTML = '<p class="muted small">couldn\u2019t load analytics</p>'; return; }
    body.innerHTML = anPastHtml(d);
  }

  const _anStack = (parts) => {
    const total = parts.reduce((a, p) => a + p.min, 0) || 1;
    return `<div class="an-stack">${parts.map((p) => `<div class="an-seg" style="width:${(p.min / total * 100).toFixed(1)}%;background:${p.color}" title="${p.label}"></div>`).join('')}</div>
      <div class="an-legend">${parts.map((p) => `<span><i style="background:${p.color}"></i>${p.label} \u00b7 ${fmtDur(p.min)}</span>`).join('')}</div>`;
  };
  const _anDayBars = (rows) => {
    const max = Math.max(1, ...rows.map((r) => Math.max(r.planned_min, r.used_min)));
    return `<div class="an-daybars">${rows.map((r) => `
      <div class="an-dcol"><div class="an-dpair">
        <span class="an-db plan" style="height:${(r.planned_min / max * 100).toFixed(1)}%" title="planned ${fmtDur(r.planned_min)}"></span>
        <span class="an-db used" style="height:${(r.used_min / max * 100).toFixed(1)}%" title="used ${fmtDur(r.used_min)}"></span>
      </div><span class="an-dlabel">${r.label}</span></div>`).join('')}</div>
      <div class="an-legend"><span><i class="plan"></i>planned</span><span><i class="used"></i>used</span></div>`;
  };
  const _anTaskBars = (rows) => {
    if (!rows.length) return '<p class="muted small">no time logged in this range yet.</p>';
    const max = Math.max(1, ...rows.map((r) => r.minutes));
    return rows.map((r) => `<div class="an-trow"><span class="an-tlabel">${esc(r.title)}</span>
      <span class="an-tbar"><span style="width:${(r.minutes / max * 100).toFixed(1)}%;background:${r.color}"></span></span>
      <span class="an-tval">${fmtDur(r.minutes)}</span></div>`).join('');
  };
  const _anWeekBars = (rows) => {
    const max = Math.max(1, ...rows.map((r) => r.minutes));
    return `<div class="an-weekbars">${rows.map((r) => `
      <div class="an-wcol"><span class="an-wb" style="height:${(r.minutes / max * 100).toFixed(1)}%" title="${fmtDur(r.minutes)}"></span>
      <span class="an-wlabel">${r.label}</span></div>`).join('')}</div>`;
  };

  function anPastHtml(d) {
    const s = d.study;
    const parts = [
      { label: 'used', min: s.used_min, color: 'var(--accent)' },
      { label: 'planned, not used', min: s.planned_not_used_min, color: 'var(--legend-plan)' },
      { label: 'free', min: s.free_min, color: 'var(--input)' },
    ];
    const most = d.most_consuming;
    return `
      <section class="an-sec"><h3>How I spent my time</h3>
        <div class="an-card">${_anStack(parts)}
          <p class="muted small" style="margin-top:10px">activity events in range \u00b7 ${fmtDur(s.activity_min)}</p></div></section>
      <section class="an-sec"><h3>Time I spent on tasks</h3>
        <div class="an-grid3">
          <div class="an-card an-big"><div class="an-bignum">${fmtDur(d.tasks_total_min)}</div><div class="muted small">total on tasks</div></div>
          <div class="an-card">${most
            ? `<div class="muted small">most time-consuming</div><div class="an-mc">${esc(most.title)}</div><div class="an-mcval" style="color:${most.color}">${fmtDur(most.minutes)}</div>`
            : '<p class="muted small">nothing logged yet</p>'}</div>
          <div class="an-card an-tasklist">${_anTaskBars(d.by_task)}</div>
        </div></section>
      <section class="an-sec"><h3>Am I following my plan?</h3>
        <div class="an-card">${d.plan_adherence.length ? _anDayBars(d.plan_adherence) : '<p class="muted small">no planned blocks in range.</p>'}</div></section>
      <section class="an-sec"><h3>Time I spent on tasks each week</h3>
        <div class="an-card">${_anWeekBars(d.by_week)}</div></section>`;
  }

  async function loadFuture() {
    const body = $('an-body'); if (!body) return;
    body.innerHTML = '<p class="muted small">loading\u2026</p>';
    let d;
    try { d = await Api.get('/analytics/future?range=' + encodeURIComponent(anRange)); }
    catch (e) { body.innerHTML = '<p class="muted small">couldn\u2019t load analytics</p>'; return; }
    body.innerHTML = anFutureHtml(d);
  }

  const _anCards = (c) => `<div class="an-cards">
    <div class="an-statcard"><div class="an-statlabel" style="color:var(--legend-plan)">available study time</div><div class="an-statnum">${fmtDur(c.available_min)}</div></div>
    <div class="an-statcard"><div class="an-statlabel">tasks due</div><div class="an-statnum">${c.tasks_due}</div></div>
    <div class="an-statcard"><div class="an-statlabel">task workload due</div><div class="an-statnum">${fmtDur(c.workload_due_min)}</div></div>
    <div class="an-statcard"><div class="an-statlabel" style="color:var(--accent)">time planned</div><div class="an-statnum">${fmtDur(c.planned_min)}</div></div>
    <div class="an-statcard"><div class="an-statlabel" style="color:var(--red)">time left to plan</div><div class="an-statnum">${fmtDur(c.left_to_plan_min)}</div></div>
  </div>`;

  const _anDonut = (parts) => {
    const total = parts.reduce((a, p) => a + p.minutes, 0);
    if (!total) return '<p class="muted small">nothing due in this range.</p>';
    let acc = 0;
    const segs = parts.map((p) => { const a0 = acc / total * 100; acc += p.minutes; const a1 = acc / total * 100; return `${p.color} ${a0.toFixed(1)}% ${a1.toFixed(1)}%`; }).join(', ');
    return `<div class="an-donutwrap"><div class="an-donut" style="background:conic-gradient(${segs})"></div>
      <div class="an-legend col">${parts.map((p) => `<span><i style="background:${p.color}"></i>${esc(p.course)} \u00b7 ${fmtDur(p.minutes)} (${p.pct}%)</span>`).join('')}</div></div>`;
  };

  const _anWeekStack = (rows) => {
    const max = Math.max(1, ...rows.map((r) => r.workload_min + r.planned_min));
    return `<div class="an-weekbars">${rows.map((r) => `
      <div class="an-wcol"><span class="an-wstack" style="height:${((r.workload_min + r.planned_min) / max * 100).toFixed(1)}%">
        <span class="an-wseg plan" style="flex:${r.planned_min}" title="planned ${fmtDur(r.planned_min)}"></span>
        <span class="an-wseg work" style="flex:${r.workload_min}" title="workload ${fmtDur(r.workload_min)}"></span>
      </span><span class="an-wlabel">${r.label}</span></div>`).join('')}</div>
      <div class="an-legend"><span><i class="plan"></i>planned</span><span><i class="work"></i>workload due</span></div>`;
  };

  function anFutureHtml(d) {
    const b = d.breakdown;
    const parts = [
      { label: 'activity', min: b.activity_min, color: 'var(--yellow)' },
      { label: 'planned', min: b.planned_min, color: 'var(--accent)' },
      { label: 'free', min: b.free_min, color: 'var(--input)' },
    ];
    return `
      ${_anCards(d.cards)}
      <section class="an-sec"><h3>Task workload due breakdown</h3>
        <div class="an-card">${_anDonut(d.by_course)}</div></section>
      <section class="an-sec"><h3>Time breakdown</h3>
        <div class="an-card">${_anStack(parts)}</div></section>
      <section class="an-sec"><h3>Task workload due each week</h3>
        <div class="an-card">${_anWeekStack(d.by_week)}</div></section>`;
  }

  // ---- Streak sub-tab (plan-adherence + rest days) -----------------------
  let streakMode = 'used';    // used | planned
  let streakStyle = 'grid';   // grid | month

  async function loadStreak() {
    const body = $('an-body'); if (!body) return;
    body.innerHTML = '<p class="muted small">loading\u2026</p>';
    let d;
    try { d = await Api.get('/streak/stats'); }
    catch (e) { body.innerHTML = '<p class="muted small">couldn\u2019t load streak</p>'; return; }
    body.innerHTML = anStreakHtml(d);
    const heat = () => { $('sg-heat').innerHTML = streakStyle === 'grid' ? _sgGrid(d) : _sgMonth(d); };
    for (const s of body.querySelectorAll('.sg-style span')) s.onclick = () => {
      streakStyle = s.dataset.st; body.querySelectorAll('.sg-style span').forEach((x) => x.classList.toggle('on', x === s)); heat();
    };
    for (const s of body.querySelectorAll('.sg-mode span')) s.onclick = () => {
      streakMode = s.dataset.md; body.querySelectorAll('.sg-mode span').forEach((x) => x.classList.toggle('on', x === s)); heat();
    };
  }

  function anStreakHtml(d) {
    const dl = (v, unit) => v == null ? `<span class="muted">${unit}</span>`
      : (v >= 0 ? `<span class="sg-up">\u25b2 ${v}% ${unit}</span>` : `<span class="sg-dn">\u25bc ${Math.abs(v)}% ${unit}</span>`);
    const dys = (n) => `${n} ${n === 1 ? 'day' : 'days'}`;
    return `
      <div class="sg-cards">
        <div class="sg-card"><div class="sg-lab">current streak <span class="flame">\u{1F525}</span></div><div class="sg-num">${dys(d.current)}</div><div class="sg-sub">longest \u00b7 ${dys(d.longest)}</div></div>
        <div class="sg-card"><div class="sg-lab">today</div><div class="sg-num">${fmtDur(d.today_min)}</div><div class="sg-sub">${dl(d.today_delta, 'vs yesterday')}</div></div>
        <div class="sg-card"><div class="sg-lab">this week</div><div class="sg-num">${fmtDur(d.week_min)}</div><div class="sg-sub">${dl(d.week_delta, 'vs last week')}</div></div>
        <div class="sg-card"><div class="sg-lab">this term</div><div class="sg-num">${fmtDur(d.term_min)}</div><div class="sg-sub">keep going</div></div>
      </div>
      <div class="sg-toolbar">
        <div class="seg sg-style"><span class="${streakStyle === 'grid' ? 'on' : ''}" data-st="grid">Grid</span><span class="${streakStyle === 'month' ? 'on' : ''}" data-st="month">Month</span></div>
        <div class="seg sg-mode"><span class="${streakMode === 'used' ? 'on' : ''}" data-md="used">Used</span><span class="${streakMode === 'planned' ? 'on' : ''}" data-md="planned">Planned</span></div>
      </div>
      <div class="sg-heat" id="sg-heat">${streakStyle === 'grid' ? _sgGrid(d) : _sgMonth(d)}</div>
      <div class="an-legend" style="margin-top:14px">less <i class="cell"></i><i class="cell l1"></i><i class="cell l2"></i><i class="cell l3"></i><i class="cell l4"></i> more</div>`;
  }

  const _mi = (iso) => (new Date(iso + 'T00:00').getDay() + 6) % 7;   // Mon=0..Sun=6

  function _sgGrid(d) {
    const key = streakMode === 'used' ? 'level' : 'plevel';
    const cols = []; let col = [];
    for (let k = 0, first = _mi(d.cells[0].day); k < first; k++) col.push(null);
    for (const c of d.cells) { col.push(c); if (_mi(c.day) === 6) { cols.push(col); col = []; } }
    if (col.length) cols.push(col);
    const cell = (c) => {
      if (!c) return '<div class="cell empty"></div>';
      const lv = c[key]; const cls = ['cell']; if (lv) cls.push('l' + lv);
      if (c.day === d.today) cls.push('today');
      if (streakMode === 'used' && c.future) cls.push('future');
      if (c.rest && streakMode === 'used' && !lv) cls.push('rest');
      const v = streakMode === 'used' ? fmtDur(c.used) : fmtDur(c.planned);
      return `<div class="${cls.join(' ')}" title="${c.day} \u00b7 ${v}${c.rest ? ' \u00b7 rest' : ''}"></div>`;
    };
    return `<div class="hmwrap"><div class="dows"><span>M</span><span>W</span><span>F</span><span>S</span></div>
      <div class="hm">${cols.map((co) => `<div class="col">${Array.from({ length: 7 }, (_, r) => cell(co[r])).join('')}</div>`).join('')}</div></div>`;
  }

  function _sgMonth(d) {
    const key = streakMode === 'used' ? 'level' : 'plevel';
    const by = {}; d.cells.forEach((c) => { by[c.day] = c; });
    const t = new Date(d.today + 'T00:00'); const y = t.getFullYear(); const m = t.getMonth();
    const pad = (new Date(y, m, 1).getDay() + 6) % 7; const days = new Date(y, m + 1, 0).getDate();
    const arr = []; for (let k = 0; k < pad; k++) arr.push(null);
    for (let dy = 1; dy <= days; dy++) {
      const iso = `${y}-${String(m + 1).padStart(2, '0')}-${String(dy).padStart(2, '0')}`;
      arr.push({ dy, iso, c: by[iso] });
    }
    const cell = (x) => {
      if (!x) return '<div class="mcell empty"></div>';
      const c = x.c; const lv = c ? c[key] : 0; const cls = ['mcell']; if (lv) cls.push('l' + lv);
      if (c && c.day === d.today) cls.push('today');
      if (c && streakMode === 'used' && c.future) cls.push('future');
      const v = c ? (streakMode === 'used' ? fmtDur(c.used) : fmtDur(c.planned)) : '0m';
      return `<div class="${cls.join(' ')}" title="${x.iso} \u00b7 ${v}">${x.dy}</div>`;
    };
    return `<div class="mcal"><div class="mcal-h">${t.toLocaleString('en', { month: 'long' })} ${y}</div>
      <div class="mcal-dows">${['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((x) => `<span>${x}</span>`).join('')}</div>
      <div class="mcal-grid">${arr.map(cell).join('')}</div></div>`;
  }

  // ---- Cushion sub-tab (feasibility snapshot) ----------------------------
  async function loadCushion() {
    const body = $('an-body'); if (!body) return;
    body.innerHTML = '<p class="muted small">loading\u2026</p>';
    try {
      const today = isoOf(new Date());
      const [cu, avail] = await Promise.all([
        Api.get('/cushion'),
        Api.get(`/cushion/availability?start=${today}&days=14`),
      ]);
      body.innerHTML = anCushionHtml(cu, avail);
    } catch (e) { body.innerHTML = '<p class="muted small">couldn\u2019t load cushion</p>'; }
  }

  const _cuAvail = (avail) => {
    if (!avail || !avail.length) return '<p class="muted small">no availability.</p>';
    const max = Math.max(1, ...avail.map((d) => d.free_min));
    return `<div class="an-weekbars cu-avail">${avail.map((d) => {
      const dt = new Date(d.date + 'T00:00');
      const lab = dt.toLocaleDateString('en-US', { weekday: 'short' }).slice(0, 2) + ' ' + dt.getDate();
      return `<div class="an-wcol"><span class="an-wb" style="height:${(d.free_min / max * 100).toFixed(1)}%" title="${d.date} \u00b7 free ${fmtDur(d.free_min)}${d.due_count ? ' \u00b7 ' + d.due_count + ' due' : ''}"></span>
        <i class="cu-duedot ${d.due_count ? 'on' : ''}"></i>
        <span class="an-wlabel">${lab}</span></div>`;
    }).join('')}</div>
      <div class="an-legend"><span><i class="cu-duedot on" style="position:static"></i>task due</span></div>`;
  };

  function anCushionHtml(cu, avail) {
    const ok = cu.feasible;
    const head = `<div class="cu-head ${ok ? 'ok' : 'bad'}">
      <div class="cu-head-lab">${ok ? 'On track' : 'Behind'}</div>
      <div class="cu-head-num">${ok ? '+' : '\u2212'}${cu.total_cushion_human.replace(' short', '')}</div>
      <div class="cu-head-sub">${ok ? 'total cushion across all your due dates'
        : 'short across your due dates \u2014 plan more time or trim scope'}</div></div>`;
    const rows = (cu.per_task || []).slice().sort((a, b) => a.cushion_min - b.cushion_min);
    const maxAbs = Math.max(60, ...rows.map((r) => Math.abs(r.cushion_min)));
    const taskRows = rows.length ? rows.map((r) => {
      const neg = r.cushion_min < 0;
      const w = (Math.abs(r.cushion_min) / maxAbs * 100).toFixed(1);
      const due = r.due_at ? new Date(r.due_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
      return `<div class="cu-row">
        <span class="cu-tlabel">${esc(r.title)}<i class="cu-due">${due} \u00b7 need ${fmtDur(r.remaining_min)}</i></span>
        <span class="cu-bar"><span class="cu-fill ${r.level}" style="width:${w}%"></span></span>
        <span class="cu-val ${r.level}">${neg ? '\u2212' : '+'}${fmtDur(r.cushion_min)}</span></div>`;
    }).join('') : '<p class="muted small">no scheduled tasks with due dates.</p>';
    const uns = (cu.unscheduled_task_ids || []).length;
    return `
      <section class="an-sec">${head}</section>
      <section class="an-sec"><h3>Cushion by task <span class="muted small">(tightest first)</span></h3>
        <div class="an-card">${taskRows}
          ${uns ? `<p class="muted small" style="margin-top:10px">${uns} task${uns === 1 ? '' : 's'} with no due date \u2014 not counted.</p>` : ''}</div></section>
      <section class="an-sec"><h3>Free study time ahead <span class="muted small">(next 14 days)</span></h3>
        <div class="an-card">${_cuAvail(avail)}</div></section>`;
  }

  // ---- Timeline sub-tab (cushion over time, by due date) -----------------
  async function loadTimeline() {
    const body = $('an-body'); if (!body) return;
    body.innerHTML = '<p class="muted small">loading\u2026</p>';
    try { body.innerHTML = anTimelineHtml(await Api.get('/cushion')); }
    catch (e) { body.innerHTML = '<p class="muted small">couldn\u2019t load timeline</p>'; }
  }

  function anTimelineHtml(cu) {
    const pts = (cu.per_task || []).map((r) => ({
      title: r.title, due: r.due_at, demand: r.cumulative_needed_min,
      capacity: r.free_until_due_min, cushion: r.cushion_min, level: r.level,
    }));
    const bad = pts.find((p) => p.cushion < 0);
    const note = !pts.length ? ''
      : bad ? `<p class="muted small" style="margin-top:8px">First crunch: <strong>${esc(bad.title)}</strong>${bad.due ? ' \u00b7 ' + new Date(bad.due).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''} \u2014 cumulative work outruns free time by ${fmtDur(bad.cushion)}.</p>`
        : '<p class="muted small" style="margin-top:8px">Cumulative work stays under your available time at every due date \u2014 you\u2019re feasible.</p>';
    return `<section class="an-sec"><h3>Cushion over time <span class="muted small">(work due vs free time, by due date)</span></h3>
      <div class="an-card">${_cuTimeline(pts)}${note}</div></section>`;
  }

  function _cuTimeline(pts) {
    if (!pts.length) return '<p class="muted small">no scheduled tasks with due dates.</p>';
    const W = 640, H = 240, L = 50, R = 14, T = 14, B = 32;
    const n = pts.length;
    const maxY = Math.max(1, ...pts.map((p) => Math.max(p.demand, p.capacity)));
    const X = (i) => L + (n === 1 ? (W - L - R) / 2 : i * (W - L - R) / (n - 1));
    const Y = (v) => T + (1 - v / maxY) * (H - T - B);
    const poly = (key) => pts.map((p, i) => `${X(i).toFixed(1)},${Y(p[key]).toFixed(1)}`).join(' ');
    const demArea = `${X(0).toFixed(1)},${Y(0).toFixed(1)} ${poly('demand')} ${X(n - 1).toFixed(1)},${Y(0).toFixed(1)}`;
    const dots = pts.map((p, i) => `<circle cx="${X(i).toFixed(1)}" cy="${Y(p.demand).toFixed(1)}" r="3.5" class="cu-dot ${p.level}"><title>${esc(p.title)}${p.due ? ' \u00b7 ' + new Date(p.due).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}
need (cumulative): ${fmtDur(p.demand)} \u00b7 free: ${fmtDur(p.capacity)}
cushion: ${p.cushion < 0 ? '\u2212' : '+'}${fmtDur(p.cushion)}</title></circle>`).join('');
    const idxs = n <= 6 ? pts.map((_, i) => i) : [0, Math.round(n / 3), Math.round(2 * n / 3), n - 1];
    const xlabs = [...new Set(idxs)].map((i) => {
      const d = pts[i].due ? new Date(pts[i].due) : null;
      return `<text x="${X(i).toFixed(1)}" y="${H - 10}" class="cu-xlab">${d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}</text>`;
    }).join('');
    return `<svg viewBox="0 0 ${W} ${H}" class="cu-svg" preserveAspectRatio="xMidYMid meet">
      <line x1="${L}" y1="${Y(0).toFixed(1)}" x2="${W - R}" y2="${Y(0).toFixed(1)}" class="cu-axis"/>
      <text x="6" y="${(Y(maxY) + 4).toFixed(1)}" class="cu-ylab">${fmtDur(maxY)}</text>
      <text x="6" y="${(Y(0) + 4).toFixed(1)}" class="cu-ylab">0</text>
      <polygon points="${demArea}" class="cu-demarea"/>
      <polyline points="${poly('capacity')}" class="cu-cap"/>
      <polyline points="${poly('demand')}" class="cu-dem"/>
      ${dots}${xlabs}
    </svg>
    <div class="an-legend" style="margin-top:8px"><span><i style="background:var(--accent)"></i>free time available</span><span><i style="background:var(--red)"></i>work due (cumulative)</span></div>`;
  }

  function canvasModal() {
    const BM = "javascript:(async()=>{try{var b=location.origin;var J=async u=>{var r=await fetch(b+u,{headers:{Accept:'application/json'}});return r.json()};var cs=[],p=1;while(p<6){var x=await J('/api/v1/courses?enrollment_state=active&per_page=100&page='+p);if(!x.length)break;cs=cs.concat(x);if(x.length<100)break;p++}var A=[];for(var c of cs){try{var as=await J('/api/v1/courses/'+c.id+'/assignments?per_page=100&bucket=upcoming');for(var a of as)A.push({id:a.id,name:a.name,due_at:a.due_at,course_id:c.id,html_url:a.html_url})}catch(e){}}await navigator.clipboard.writeText(JSON.stringify({courses:cs.map(c=>({id:c.id,name:c.name})),assignments:A}));alert('scholar: copied '+A.length+' assignments from '+cs.length+' courses. Paste into scholar.')}catch(e){alert('scholar failed: '+e)}})();";
    const { ov, close } = modal(`
      <h2>import</h2>
      <div class="seg cv-seg">
        <span data-tab="token" class="on">Canvas token</span>
        <span data-tab="ics">Calendar feed</span>
        <span data-tab="script">Quick script</span>
        <span data-tab="syllabus">Syllabus PDF</span>
      </div>

      <div class="cv-panel" data-panel="token">
        <p class="muted small">token: psu.instructure.com → Account → Settings → + New Access Token.
          Stored in your own database, used server-side only.</p>
        <div class="frow"><label>base url</label>
          <input id="m-url" value="${esc(S.canvas.base_url || 'https://psu.instructure.com')}" /></div>
        <div class="frow"><label>access token</label>
          <input id="m-tok" type="password" placeholder="${S.canvas.configured ? '•••••• (saved)' : 'paste token'}" /></div>
        <button class="primary" id="cv-save-token">save</button>
        <p class="muted small" style="margin-top:12px">Can't make a token (school disabled it)? Use
          <a class="lnk" data-go="ics">Calendar feed</a> or the <a class="lnk" data-go="script">Quick script</a>.</p>
      </div>

      <div class="cv-panel" data-panel="ics" hidden>
        <p class="muted small">No token, no cookie. In Canvas: <strong>Calendar → Calendar Feed</strong>, copy the link.
          scholar polls it server-side and turns assignment due dates into tasks.</p>
        <div class="frow"><label>calendar feed URL ${S.canvas.ics_configured ? '· <span class="ok-i">saved</span>' : ''}</label>
          <input id="m-ics" placeholder="https://psu.instructure.com/feeds/calendars/user_….ics" /></div>
        <div class="btns"><button class="ghost" id="cv-save-ics">save</button>
          <button class="primary" id="cv-sync-ics">save &amp; sync now</button></div>
        <div class="cv-auto">
          <label class="cv-auto-row"><input type="checkbox" id="cv-autosync" /> auto-sync in the background</label>
          <label class="cv-auto-hours">every <input id="cv-autohours" type="number" min="1" max="168" value="12" /> hours</label>
          <div class="muted small" id="cv-lastsync"></div>
        </div>
      </div>

      <div class="cv-panel" data-panel="script" hidden>
        <p class="muted small">For when token creation is disabled. Make a bookmark whose URL is the code below
          (or paste it into the browser console while logged into Canvas). It copies your courses + assignments
          to your clipboard — works on http too.</p>
        <label>1 · the script</label>
        <textarea id="cv-bm" class="cv-code" readonly rows="3">${BM}</textarea>
        <button class="ghost" id="cv-copy-bm">copy script</button>
        <label style="margin-top:14px">2 · run it on Canvas, then paste what it copied</label>
        <textarea id="cv-paste" class="cv-code" rows="3" placeholder="paste the copied data here…"></textarea>
        <button class="primary" id="cv-import">import pasted data</button>
      </div>

      <div class="cv-panel" data-panel="syllabus" hidden>
        <p class="muted small">No Canvas? Upload a syllabus (PDF or .txt) and scholar pulls out the dated
          assignments for you to review before anything is added. Reads US and international date formats.</p>
        <div class="frow"><label>syllabus file</label>
          <input id="syl-file" type="file" accept=".pdf,.txt,text/plain,application/pdf" /></div>
        <div class="syl-opts">
          <label>course (optional)<input id="syl-course" placeholder="e.g. CMPSC 465" /></label>
          <label>term year<input id="syl-year" type="number" value="${new Date().getFullYear()}" /></label>
          <label class="syl-df"><input id="syl-dayfirst" type="checkbox" /> day-first dates (13/09)</label>
        </div>
        <button class="primary" id="syl-parse">read syllabus</button>
        <div id="syl-results" style="margin-top:14px"></div>
      </div>

      <div class="actions"><span class="spacer"></span><button class="ghost" data-m="cancel">close</button></div>`,
      () => {});

    // tab switching
    const show = (name) => {
      ov.querySelectorAll('.cv-seg span').forEach((s) => s.classList.toggle('on', s.dataset.tab === name));
      ov.querySelectorAll('.cv-panel').forEach((p) => { p.hidden = p.dataset.panel !== name; });
    };
    ov.querySelectorAll('.cv-seg span').forEach((s) => { s.onclick = () => show(s.dataset.tab); });
    ov.querySelectorAll('[data-go]').forEach((a) => { a.onclick = () => show(a.dataset.go); });

    ov.querySelector('#cv-save-token').onclick = async () => {
      const body = { canvas_base_url: ov.querySelector('#m-url').value.trim() };
      const tok = ov.querySelector('#m-tok').value.trim();
      if (tok) body.canvas_token = tok;
      await Api.put('/config/settings', body); await loadAll(); toast('canvas token saved — hit sync');
    };
    const saveIcs = async () => {
      const u = ov.querySelector('#m-ics').value.trim();
      if (!u) { toast('paste the feed URL first'); return false; }
      await Api.put('/config/settings', { canvas_ics_url: u }); await loadAll(); return true;
    };
    ov.querySelector('#cv-save-ics').onclick = async () => { if (await saveIcs()) toast('feed saved'); };
    ov.querySelector('#cv-sync-ics').onclick = async () => {
      if (!(await saveIcs())) return;
      try { const r = await Api.post('/integrations/canvas/sync-ics');
        toast(`feed: ${r.created} new, ${r.updated} updated (${r.events} events)`); close(); }
      catch (e) { toast('feed sync failed — check the URL'); }
    };
    const auto = ov.querySelector('#cv-autosync');
    if (auto) {
      const hrs = ov.querySelector('#cv-autohours');
      const lastEl = ov.querySelector('#cv-lastsync');
      auto.checked = !!S.canvas.autosync;
      hrs.value = S.canvas.sync_hours || 12;
      lastEl.textContent = S.canvas.last_sync
        ? 'last auto-sync: ' + new Date(S.canvas.last_sync).toLocaleString()
        : 'never auto-synced yet';
      const saveAuto = async () => {
        const hours = +hrs.value || 12;
        await Api.put('/config/settings', { canvas_autosync: auto.checked, canvas_sync_hours: hours });
        S.canvas.autosync = auto.checked; S.canvas.sync_hours = hours;
        toast(auto.checked ? `auto-sync on \u00b7 every ${hours}h` : 'auto-sync off');
      };
      auto.onchange = saveAuto;
      hrs.onchange = () => { if (auto.checked) saveAuto(); };
    }
    ov.querySelector('#cv-copy-bm').onclick = async () => {      try { await navigator.clipboard.writeText(ov.querySelector('#cv-bm').value); toast('script copied'); }
      catch (e) { ov.querySelector('#cv-bm').select(); toast('press ⌘/Ctrl-C to copy'); }
    };
    ov.querySelector('#cv-import').onclick = async () => {
      let data; try { data = JSON.parse(ov.querySelector('#cv-paste').value.trim()); }
      catch (e) { toast('that doesn\u2019t look like the copied data'); return; }
      try { const r = await Api.post('/integrations/canvas/import', data);
        toast(`imported: ${r.created} new, ${r.updated} updated`); close(); }
      catch (e) { toast('import failed'); }
    };

    // --- syllabus PDF: read -> review -> import ---
    let sylItems = [];
    const readB64 = (file) => new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result).split(',')[1] || '');
      r.onerror = rej; r.readAsDataURL(file);
    });
    const doImport = async () => {
      const items = [...ov.querySelectorAll('.syl-row')]
        .filter((r) => r.querySelector('.syl-ck').checked)
        .map((r) => ({ title: r.querySelector('.syl-t').value.trim(),
                       due_date: r.querySelector('.syl-d').value || null,
                       category: r.querySelector('.syl-c').value.trim() }))
        .filter((x) => x.title);
      if (!items.length) { toast('nothing selected'); return; }
      try {
        const r = await Api.post('/integrations/syllabus/import',
          { course_name: ov.querySelector('#syl-course').value.trim() || null, items });
        toast(`imported ${r.created} task${r.created === 1 ? '' : 's'}${r.course ? ' \u2192 ' + r.course : ''}`);
        await loadAll(); close();
      } catch (e) { toast('import failed'); }
    };
    const renderSyl = (r) => {
      const res = ov.querySelector('#syl-results');
      if (!sylItems.length) {
        res.innerHTML = `<p class="muted small">${esc(r.note || 'no dated assignments found \u2014 try the day-first toggle, or add them by hand.')}</p>`;
        return;
      }
      res.innerHTML = `<div class="syl-head">${sylItems.length} found \u00b7 uncheck any you don\u2019t want, edit titles/dates inline</div>
        <div class="syl-rows">${sylItems.map((it, i) => `
          <div class="syl-row">
            <input type="checkbox" class="syl-ck" data-i="${i}" checked />
            <input class="syl-t" value="${esc(it.title)}" />
            <input class="syl-d" type="date" value="${it.due_date}" />
            <input class="syl-c" value="${esc(it.category)}" placeholder="category" />
          </div>`).join('')}</div>
        <button class="primary" id="syl-import" style="margin-top:12px">import selected</button>`;
      res.querySelector('#syl-import').onclick = doImport;
    };
    ov.querySelector('#syl-parse').onclick = async () => {
      const f = ov.querySelector('#syl-file').files[0];
      if (!f) { toast('choose a PDF or text file first'); return; }
      const res = ov.querySelector('#syl-results');
      res.innerHTML = '<p class="muted small">reading\u2026</p>';
      try {
        const data_b64 = await readB64(f);
        const r = await Api.post('/integrations/syllabus/parse', {
          filename: f.name, data_b64,
          year: +ov.querySelector('#syl-year').value || undefined,
          dayfirst: ov.querySelector('#syl-dayfirst').checked,
        });
        sylItems = r.items || [];
        renderSyl(r);
      } catch (e) { res.innerHTML = '<p class="muted small">couldn\u2019t read that file</p>'; }
    };
  }

  // ============================================================
  //  SETTINGS  (full rebuild — left rail + single-scroll sections)
  // ============================================================
  async function settingsModal() {
    const awake = await Api.get('/awake');
    const termCfg = await Api.get('/config/term');
    const t = termCfg.term || {};
    const aw = Object.fromEntries(awake.map((a) => [a.weekday, a]));
    const st = S.settings;
    const accent = st.accent || '#3D7DFF';
    const ACC = ['#3D7DFF', '#AF52DE', '#FF2D78', '#FF3B30', '#FF9500', '#FFCC00', '#34C759', '#00B8A9'];
    const sel = (v, x) => (v === x ? 'selected' : '');

    // ---- field helpers (consistent rows) -------------------------------
    const row = (label, hint, control) => `
      <div class="srow">
        <div class="srow-l"><div class="srow-label">${label}</div>${hint ? `<div class="srow-hint">${hint}</div>` : ''}</div>
        <div class="srow-c">${control}</div>
      </div>`;
    const group = (title, rows) => `${title ? `<div class="sgroup-title">${title}</div>` : ''}<div class="sgroup">${rows}</div>`;

    // ---- panes ---------------------------------------------------------
    const paneTerm = group('location & timezone',
        row('Country', '', `<select id="m-country"></select>`) +
        row('School timezone', 'where deadlines are anchored', `<select id="m-school-tz"></select>`) +
        row('Your timezone', 'awake hours follow this', `<select id="m-home-tz"></select>`)
      ) + group('term dates',
        row('Classes start', '', `<input id="m-ts" type="date" value="${t.classes_start || ''}" />`) +
        row('Classes end', '', `<input id="m-te" type="date" value="${t.classes_end || ''}" />`) +
        row('Exams end', '', `<input id="m-tx" type="date" value="${t.exam_end || ''}" />`)
      );

    const panePers = group('study planning',
        row('Minimum study block', '', `<input id="m-min" type="number" value="${st.min_block_min}" /> <span class="unit">min</span>`) +
        row('Start ahead', 'begin tasks this many days early', `<input id="m-ahead" type="number" value="${st.start_ahead_days}" /> <span class="unit">days</span>`) +
        row('Cushion turns yellow at', '% of needed time left', `<input id="m-yel" type="number" value="${st.yellow_threshold_pct}" /> <span class="unit">%</span>`) +
        row('Week starts on', '', `<select id="m-wkstart"><option value="6" ${sel(st.week_start, 6)}>Sunday</option><option value="0" ${sel(st.week_start, 0)}>Monday</option></select>`) +
        row('Default view', '', `<select id="m-defview">${['week', 'day', 'month'].map((v) => `<option ${sel(st.default_view || 'week', v)}>${v}</option>`).join('')}</select>`) +
        row('Calendar scrolls to', 'where the week/day view opens', `<input id="m-daystart" type="time" value="${pad(Math.floor((st.day_start_min ?? 480) / 60))}:${pad((st.day_start_min ?? 480) % 60)}" />`)
      ) + `<div class="sgroup-title">awake time</div>
        <div class="sgroup awake-block">
          <div class="awake-default">
            <span class="muted small">usually awake</span>
            <input type="time" id="awk-def-s" value="08:00" />
            <span class="muted">→</span>
            <input type="time" id="awk-def-e" value="23:30" />
            <button type="button" class="ghost xs" id="awk-apply-all">apply to all</button>
          </div>
          <div class="awake-presets">
            <button type="button" class="ghost xs" data-preset="weekday">set weekdays</button>
            <button type="button" class="ghost xs" data-preset="weekend">set weekend</button>
          </div>
          <div class="awake-days" id="awake-days"></div>
          ${DAYS.map((d, i) => `<input type="hidden" data-aws="${i}" value="${aw[i]?.start_min ?? 480}" /><input type="hidden" data-awe="${i}" value="${aw[i]?.end_min ?? 1410}" />`).join('')}
        </div>`;

    const paneAppear = group('',
        row('Theme', '', `<select id="m-theme"><option value="dark" ${sel(st.theme || 'dark', 'dark')}>dark</option><option value="light" ${sel(st.theme, 'light')}>light</option></select>`) +
        row('Density', '', `<select id="m-density"><option value="1" ${sel(+st.density || 1, 1)}>comfortable</option><option value="0.85" ${sel(+st.density, 0.85)}>compact</option></select>`) +
        row('Font size', '', `<select id="m-font"><option value="0.92" ${sel(+st.fontscale, 0.92)}>small</option><option value="1" ${sel(+st.fontscale || 1, 1)}>normal</option><option value="1.12" ${sel(+st.fontscale, 1.12)}>large</option></select>`)
      ) + group('accent',
        row('Color', '', `<div class="swatches" id="m-accent">${ACC.map((c) => `<span class="swatch ${accent === c ? 'sel' : ''}" data-c="${c}" style="background:${c}"></span>`).join('')}</div>`)
      );

    const paneNotif = `<p class="set-sub">Browser notifications aren't wired yet — placeholders for the next phase. <span class="soon-badge">coming soon</span></p>` +
      group('',
        row('Should be working on', 'nudge me about what\'s next', `<input type="checkbox" disabled />`) +
        row('Overdue', 'notify when a task slips', `<input type="checkbox" disabled />`) +
        row('Planned task starts', 'remind me before a block', `<input type="checkbox" disabled />`)
      );

    const paneAcct = `<p class="set-sub">Single-user, self-hosted — localhost testing auto-creates a browser key.</p>` +
      group('',
        row('Display name', '', `<input id="m-name" type="text" value="${esc(st.display_name || '')}" placeholder="your name" />`)
      ) + group('api key',
        row('Mint a new key', 'keys are shown once', `<button class="ghost" id="m-newkey">mint</button>`) +
        `<div class="srow" id="m-newkey-row" style="display:none"><div class="srow-l"><div class="srow-label">Your key</div></div><div class="srow-c"><code id="m-newkey-out"></code></div></div>`
      ) + group('minted keys', `<div id="m-keylist" class="muted small">loading…</div>`);

    const SECTIONS = [
      ['term', 'Term', 'where you study and when the term runs', paneTerm],
      ['pers', 'Personalization', 'how the planner schedules your time', panePers],
      ['appear', 'Appearance', 'make it yours', paneAppear],
      ['notif', 'Notifications', '', paneNotif],
      ['acct', 'Account', '', paneAcct],
    ];

    const nav = SECTIONS.map(([id, label], i) =>
      `<button class="snav-item ${i === 0 ? 'active' : ''}" data-go="${id}">${label}</button>`).join('');
    const panes = SECTIONS.map(([id, label, sub, body], i) =>
      `<section class="spane ${i === 0 ? '' : 'hidden'}" data-pane="${id}">
        <h2 class="spane-title">${label}</h2>${sub ? `<p class="set-sub">${sub}</p>` : ''}${body}
      </section>`).join('');

    const { ov, close } = modal(`
      <div class="settings2">
        <aside class="snav"><div class="snav-head">settings</div>${nav}</aside>
        <div class="sscroll">
          <div class="spanes">${panes}</div>
          <div class="sactions">
            <button class="ghost" data-m="cancel">cancel</button>
            <button class="primary" data-m="save">save</button>
          </div>
        </div>
      </div>`, async (act, ovEl) => { if (act === 'save') await saveSettings(ovEl); });

    ov.querySelector('.modal').classList.add('settings2-modal');

    // nav switching (animated crossfade handled by CSS on .spane)
    for (const b of ov.querySelectorAll('[data-go]')) {
      b.onclick = () => {
        for (const n of ov.querySelectorAll('.snav-item')) n.classList.toggle('active', n === b);
        for (const p of ov.querySelectorAll('.spane')) p.classList.toggle('hidden', p.dataset.pane !== b.dataset.go);
        ov.querySelector('.sscroll').scrollTop = 0;
      };
    }

    wireSwatches(ov);
    wireAwake(ov);
    await initSettingsTz(ov);

    const mk = ov.querySelector('#m-newkey');
    if (mk) mk.onclick = async () => {
      const r = ov.querySelector('#m-newkey-row'), out = ov.querySelector('#m-newkey-out');
      try { const k = await Api.post('/auth/keys?label=ui'); out.textContent = k.api_key || '(minted)'; }
      catch (e) { out.textContent = 'mint failed: ' + e.message; }
      if (r) r.style.display = 'flex';
      await renderKeyList(ov);
    };
    if (ov.querySelector('#m-keylist')) await renderKeyList(ov);
  }

  async function renderKeyList(ov) {
    const host = ov.querySelector('#m-keylist');
    if (!host) return;
    let keys;
    try { keys = await Api.get('/auth/keys'); }
    catch (e) { host.textContent = 'could not load keys'; return; }
    if (!keys.length) { host.textContent = 'no keys minted yet'; return; }
    host.innerHTML = keys.map((k) => `<div class="srow">
        <div class="srow-l"><div class="srow-label">${esc(k.label)}</div>
          <div class="srow-hint">${new Date(k.created_at).toLocaleString()}${k.revoked ? ' · revoked' : ''}</div></div>
        <div class="srow-c">${k.revoked ? '' : `<button class="ghost xs" data-revoke="${k.id}">revoke</button>`}</div>
      </div>`).join('');
    host.querySelectorAll('[data-revoke]').forEach((b) => b.onclick = async () => {
      b.disabled = true;
      try { await Api.post(`/auth/keys/${b.dataset.revoke}/revoke`); await renderKeyList(ov); }
      catch (e) { b.disabled = false; toast('revoke failed', true); }
    });
  }

  async function saveSettings(ov) {
    await Api.put('/config/settings', {
      min_block_min: +ov.querySelector('#m-min').value || 30,
      start_ahead_days: +ov.querySelector('#m-ahead').value || 3,
      yellow_threshold_pct: +ov.querySelector('#m-yel').value || 40,
      week_start: +ov.querySelector('#m-wkstart').value,
      default_view: ov.querySelector('#m-defview').value,
      day_start_min: (() => {
        const [h, m] = (ov.querySelector('#m-daystart')?.value || '08:00').split(':').map(Number);
        return h * 60 + m;
      })(),
      theme: ov.querySelector('#m-theme').value,
      accent: ov.querySelector('#m-accent .swatch.sel')?.dataset.c || '#3D7DFF',
      density: +ov.querySelector('#m-density').value,
      fontscale: +ov.querySelector('#m-font').value,
      home_tz: ov.querySelector('#m-home-tz').value,
      school_tz: ov.querySelector('#m-school-tz').value,
      country: ov.querySelector('#m-country').value,
      display_name: ov.querySelector('#m-name')?.value || '',
    });
    await Api.put('/config/term', {
      classes_start: ov.querySelector('#m-ts').value || null,
      classes_end: ov.querySelector('#m-te').value || null,
      exam_end: ov.querySelector('#m-tx').value || null,
    });
    await Api.put('/awake', DAYS.map((_, i) => ({
      weekday: i,
      start_min: +ov.querySelector(`[data-aws="${i}"]`).value,
      end_min: +ov.querySelector(`[data-awe="${i}"]`).value,
    })));
    await loadAll();
    toast('settings saved');
  }

  async function initSettingsTz(ov) {
    const cSel = ov.querySelector('#m-country');
    const homeSel = ov.querySelector('#m-home-tz');
    const schoolSel = ov.querySelector('#m-school-tz');
    if (!cSel) return;
    const country = S.settings.country || 'US';
    let data;
    try { data = await Api.get('/config/timezones?country=' + country); }
    catch { data = { countries: ['US'], zones: [], all: [] }; }
    cSel.innerHTML = data.countries.map((c) => `<option value="${c}" ${c === country ? 'selected' : ''}>${c}</option>`).join('');
    const fillTz = (s, selected, zones, all) => {
      const opts = (zones && zones.length ? zones.map((z) => [z.id, z.label]) : (all || []).map((z) => [z, z]));
      s.innerHTML = opts.map(([id, lbl]) => `<option value="${id}" ${id === selected ? 'selected' : ''}>${lbl}</option>`).join('');
    };
    fillTz(schoolSel, S.settings.school_tz || 'America/New_York', data.zones, data.all);
    fillTz(homeSel, S.settings.home_tz || 'America/New_York', data.zones, data.all);
    cSel.onchange = async () => {
      const d = await Api.get('/config/timezones?country=' + cSel.value);
      fillTz(schoolSel, schoolSel.value, d.zones, d.all);
      fillTz(homeSel, homeSel.value, d.zones, d.all);
    };
  }

  function wireAwake(ov) {
    const wrap = ov.querySelector('.awake-block'); if (!wrap) return;
    const daysEl = ov.querySelector('#awake-days');
    const DAY_MIN = 1440;
    const get = (i) => ({ s: +ov.querySelector(`[data-aws="${i}"]`).value, e: +ov.querySelector(`[data-awe="${i}"]`).value });
    const set = (i, s, e) => {
      s = Math.max(0, Math.min(DAY_MIN, Math.round(s / 15) * 15));
      e = Math.max(s + 15, Math.min(DAY_MIN, Math.round(e / 15) * 15));
      ov.querySelector(`[data-aws="${i}"]`).value = s;
      ov.querySelector(`[data-awe="${i}"]`).value = e;
    };
    const hm = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
    const hmToM = (v) => { const [h, m] = v.split(':').map(Number); return h * 60 + m; };
    let editing = -1;

    const render = () => {
      daysEl.innerHTML = DAYS.map((d, i) => {
        const { s, e } = get(i);
        const left = (s / DAY_MIN) * 100, width = ((e - s) / DAY_MIN) * 100;
        return `<div class="awk-day ${editing === i ? 'open' : ''}" data-day="${i}">
          <span class="awk-lbl">${d}</span>
          <div class="awk-track" data-track="${i}"><div class="awk-band" style="left:${left}%;width:${width}%;">
            <span class="awk-h awk-h-s" data-h="s"></span><span class="awk-h awk-h-e" data-h="e"></span>
          </div></div>
          <span class="awk-time muted small">${hm(s)}–${hm(e)}</span>
          <div class="awk-edit"><input type="time" class="awk-edit-s" value="${hm(s)}" /><span class="muted">→</span><input type="time" class="awk-edit-e" value="${hm(e)}" /></div>
        </div>`;
      }).join('');
      for (const r of daysEl.querySelectorAll('.awk-day')) {
        const i = +r.dataset.day;
        r.querySelector('.awk-lbl').onclick = () => { editing = editing === i ? -1 : i; render(); };
        r.querySelector('.awk-time').onclick = () => { editing = editing === i ? -1 : i; render(); };
        const es = r.querySelector('.awk-edit-s'), ee = r.querySelector('.awk-edit-e');
        if (es) es.onchange = () => { const { e } = get(i); set(i, hmToM(es.value), e); render(); };
        if (ee) ee.onchange = () => { const { s } = get(i); set(i, s, hmToM(ee.value)); render(); };
        const track = r.querySelector('.awk-track');
        for (const h of r.querySelectorAll('.awk-h')) {
          h.onmousedown = (ev) => {
            ev.preventDefault();
            const which = h.dataset.h, rect = track.getBoundingClientRect();
            const move = (e2) => {
              const pct = Math.max(0, Math.min(1, (e2.clientX - rect.left) / rect.width));
              const m = Math.round((pct * DAY_MIN) / 15) * 15;
              const cur = get(i);
              if (which === 's') set(i, m, cur.e); else set(i, cur.s, m);
              render();
            };
            const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
            document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
          };
        }
      }
    };
    const applyRange = (idxs) => {
      const s = hmToM(ov.querySelector('#awk-def-s').value), e = hmToM(ov.querySelector('#awk-def-e').value);
      idxs.forEach((i) => set(i, s, e)); render();
    };
    ov.querySelector('#awk-apply-all').onclick = () => applyRange([0, 1, 2, 3, 4, 5, 6]);
    for (const b of wrap.querySelectorAll('[data-preset]'))
      b.onclick = () => applyRange(b.dataset.preset === 'weekday' ? [0, 1, 2, 3, 4] : [5, 6]);
    render();
  }

  // ---------- toast ----------
  function toast(msg, bad) {
    let el = $('toast');
    if (!el) {
      el = document.createElement('div'); el.id = 'toast';
      el.style.cssText = 'position:fixed;bottom:18px;left:50%;transform:translateX(-50%);' +
        'background:var(--elev);border:1px solid var(--line-mid);border-radius:999px;' +
        'padding:8px 18px;z-index:99;font-size:12px;max-width:80vw';
      document.body.appendChild(el);
    }
    el.style.color = bad ? 'var(--red)' : 'var(--fg)';
    el.textContent = msg;
    el.style.display = 'block';
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { el.style.display = 'none'; }, 3500);
  }

  boot();
})();
