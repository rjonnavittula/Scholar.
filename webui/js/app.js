/* app.js — state, boot, sidebar, modals, glue. */
(() => {
  const $ = (id) => document.getElementById(id);
  const pad = (n) => String(n).padStart(2, '0');
  const isoOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const minToHM = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
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
    if (!Api.hasKey()) return showGate();
    try { await Api.get('/config/settings'); } catch (e) { return showGate(); }
    $('gate').classList.add('hidden');
    $('app').classList.remove('hidden');
    Cal.mount($('calendar'), S, { onPlan, onMovePlanned, onBlockMenu });
    Panel.mount($('task-groups'), S, { onTaskAction });
    wireChrome();
    await loadAll();
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
        Api.get('/streak?days=9'),
      ]);
    Object.assign(S, { settings, courses, activities, tasks, planned, cushion,
                       availability: avail, canvas, streak });
    S.cushionByTask = Object.fromEntries((cushion.per_task || []).map((c) => [c.task_id, c]));
    renderAll();
  }

  function renderAll() {
    renderSidebar(); renderTop(); renderStreak(); Cal.render(); Panel.render();
    const list = document.getElementById('tasklist');
    if (list && !list.classList.contains('hidden')) renderTaskList(list);
  }

  // ---------- top chrome ----------
  function renderTop() {
    const a = S.weekDays[0], b = S.weekDays[6];
    $('week-label').textContent =
      `${a.toLocaleDateString(undefined, { month: 'long', day: 'numeric' })} – ` +
      `${b.toLocaleDateString(undefined, { month: b.getMonth() === a.getMonth() ? undefined : 'long', day: 'numeric' })}`;
    const chip = $('cushion-chip');
    const c = S.cushion || {};
    chip.textContent = `cushion ${c.total_cushion_human || '…'}`;
    chip.className = 'cushion-chip ' + (c.feasible ? 'ok' : 'bad');
  }

  function renderStreak() {
    const el = document.getElementById('streak'); if (!el) return;
    const st = S.streak || { current: 0, days: [] };
    el.innerHTML = '<span class="flame">\u{1F525}</span>' +
      st.days.map((d) => `<span class="dot l${d.level}" title="${d.day}: ${d.score}"></span>`).join('') +
      `<span class="n">${st.current}d</span>`;
  }

  function setCalView(view) {
    S.view = view;
    for (const b of document.querySelectorAll('#viewtabs [data-view]'))
      b.classList.toggle('active', b.dataset.view === view);
    if (view !== 'nextN') document.getElementById('view-n').value = '';
    Cal.setView ? Cal.setView(view, S.viewN || 7) : null;
    loadAll();
  }

  function wireChrome() {
    for (const b of document.querySelectorAll('#viewtabs [data-view]'))
      b.onclick = () => setCalView(b.dataset.view);
    const vn = document.getElementById('view-n');
    if (vn) vn.onchange = () => { if (vn.value) { S.viewN = +vn.value; setCalView('nextN'); } };
    $('nav-today').onclick = () => { S.weekStart = mondayOf(new Date()); loadAll(); };
    $('nav-prev').onclick = () => { S.weekStart = addDays(S.weekStart, -7); loadAll(); };
    $('nav-next').onclick = () => { S.weekStart = addDays(S.weekStart, 7); loadAll(); };
    $('btn-add-task').onclick = () => taskModal();
    $('btn-add-course').onclick = () => courseModal();
    $('btn-add-activity').onclick = () => activityModal();
    $('btn-canvas-cfg').onclick = () => canvasModal();
    $('btn-canvas-sync').onclick = syncCanvas;
    $('btn-settings').onclick = () => settingsModal();
    document.querySelector('[data-view="insights"]').onclick =
      () => toast('cushion charts, timeline & analytics land in phase 5');
    wireTabs();
  }

  // ---------- calendar / task-list tab switch (fix 6) ----------
  function wireTabs() {
    const tabs = document.querySelectorAll('.topbar .tab');
    if (tabs.length < 2) return;
    const [calTab, listTab] = tabs;
    calTab.classList.remove('muted'); listTab.classList.remove('muted');
    calTab.onclick = () => setView('calendar', calTab, listTab);
    listTab.onclick = () => setView('list', listTab, calTab);
  }
  function setView(view, on, off) {
    on.classList.add('active'); off.classList.remove('active');
    const cal = $('calendar');
    let list = $('tasklist');
    if (view === 'list') {
      cal.classList.add('hidden');
      if (!list) { list = document.createElement('div'); list.id = 'tasklist';
        list.className = 'tasklist'; cal.parentNode.appendChild(list); }
      list.classList.remove('hidden');
      renderTaskList(list);
    } else {
      cal.classList.remove('hidden');
      if (list) list.classList.add('hidden');
    }
  }
  function renderTaskList(el) {
    const open = S.tasks.filter((t) => t.status !== 'done')
      .sort((a, b) => (a.due_at || '9999').localeCompare(b.due_at || '9999'));
    const byCourse = {};
    for (const t of open) (byCourse[t.course_id ?? 'none'] ??= []).push(t);
    const cname = Object.fromEntries(S.courses.map((c) => [c.id, c]));
    el.innerHTML = open.length ? Object.entries(byCourse).map(([cid, ts]) => {
      const c = cname[cid];
      return `<div class="tl-group">
        <div class="tl-course"><span class="dot" style="background:${c?.color || '#8A7F73'}"></span>${esc(c?.name || 'unassigned')}</div>
        ${ts.map((t) => {
          const cu = S.cushionByTask[t.id];
          const lv = cu ? cu.level : 'none';
          const cuTxt = cu ? `${cu.cushion_min < 0 ? '-' : ''}${Math.abs(Math.round(cu.cushion_min/60))}h cushion` : 'no due date';
          return `<div class="tl-row">
            <span class="cu ${lv}">${cuTxt}</span>
            <div class="grow"><div>${esc(t.title)}</div>
              <div class="muted small">${t.due_at ? 'due ' + Api.dayInZone(t.due_at, (S.settings.school_tz || 'America/New_York')) : 'unscheduled'} \u00b7 ${t.time_spent_min}/${t.time_needed_min}m</div></div>
            <button class="ghost small-btn" data-tl-done="${t.id}">done</button>
            <button class="ghost small-btn" data-tl-edit="${t.id}">edit</button>
          </div>`;
        }).join('')}
      </div>`;
    }).join('') : '<p class="muted">no open tasks. add one, or sync Canvas.</p>';
    for (const b of el.querySelectorAll('[data-tl-done]'))
      b.onclick = () => onTaskAction('done', +b.dataset.tlDone).then(() => renderTaskList(el));
    for (const b of el.querySelectorAll('[data-tl-edit]'))
      b.onclick = () => onTaskAction('edit', +b.dataset.tlEdit);
  }

  // ---------- sidebar ----------
  function renderSidebar() {
    $('course-list').innerHTML = S.courses.map((c) => `
      <div class="side-item clickable" data-edit-course="${c.id}">
        <span class="dot" style="background:${c.color}"></span>
        <span class="nm">${esc(c.name)}</span>
        ${c.source === 'canvas' ? '<span class="meta">canvas</span>' : ''}
        <button class="x" data-del-course="${c.id}">✕</button>
      </div>`).join('') || '<p class="muted small">no courses yet</p>';

    const actGroups = {};
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
      <div class="side-item clickable" data-edit-act="${g.ids.join(',')}"
           data-title="${esc(g.title)}" data-color="${g.color}"
           data-days="${g.days.join(',')}" data-s="${g.start_min}" data-e="${g.end_min}">
        <span class="dot" style="background:${g.color}"></span>
        <span class="nm">${esc(g.title)}</span>
        <span class="meta">${dayAbbr(g.days)} ${minToHM(g.start_min)}</span>
        <button class="x" data-del-act="${g.ids.join(',')}">✕</button>
      </div>`).join('') || '<p class="muted small">no activities yet</p>';

    $('canvas-status').textContent = S.canvas.configured
      ? `linked · ${S.canvas.base_url.replace(/^https?:\/\//, '')}` : 'not configured';
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
        }); };
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

  function onBlockMenu(block) {
    const t = S.tasks.find((x) => x.id === block.task_id) || {};
    const dur = Math.round((new Date(block.end_at) - new Date(block.start_at)) / 60000);
    modal(`
      <h2>${esc(t.title || 'planned block')}</h2>
      <p class="muted small">${block.start_at.slice(0, 16).replace('T', ' · ')} — ${dur} min</p>
      <div class="actions">
        <button class="ghost" data-m="del">remove block</button>
        ${block.completed ? '' : '<button class="primary" data-m="done">✓ studied it — log time</button>'}
      </div>`, async (act) => {
      if (act === 'del') await Api.del('/planned/' + block.id);
      if (act === 'done') await Api.patch('/planned/' + block.id, { completed: true });
      await loadAll();
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
    const { ov } = modal(`
      <h2>${t ? 'edit task' : 'new task'}</h2>
      <div class="frow"><label>title</label>
        <input id="m-title" value="${esc(t?.title || '')}" placeholder="Homework 4…" /></div>
      <div class="frow">
        <div><label>course</label><select id="m-course">
          <option value="">—</option>
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
          <div class="tz-pick">
            <select id="m-tz-country"></select>
            <select id="m-tz-zone"></select>
          </div></div>
        <div><label>time needed</label>
          <div class="dur" id="m-need" data-min="${t?.time_needed_min ?? 60}">
            <div class="dseg">
              <button type="button" class="dstep" data-k="h" data-d="1">\u25B2</button>
              <input class="dh" type="text" inputmode="numeric" maxlength="2"
                value="${Math.floor((t?.time_needed_min ?? 60) / 60)}" /><i>h</i>
              <button type="button" class="dstep" data-k="h" data-d="-1">\u25BC</button>
            </div>
            <div class="dseg">
              <button type="button" class="dstep" data-k="m" data-d="1">\u25B2</button>
              <input class="dm" type="text" inputmode="numeric" maxlength="2"
                value="${String((t?.time_needed_min ?? 60) % 60).padStart(2, '0')}" /><i>m</i>
              <button type="button" class="dstep" data-k="m" data-d="-1">\u25BC</button>
            </div>
          </div></div>
      </div>
      ${ACTIONS('save')}`,
      async (act, ovEl) => {
        if (act !== 'save') return;
        const dd = ovEl.querySelector('#m-due-d').value;
        const body = {
          title: ovEl.querySelector('#m-title').value.trim() || 'untitled',
          course_id: +ovEl.querySelector('#m-course').value || null,
          category: ovEl.querySelector('#m-cat').value,
          due_at: dd ? `${dd}T${ovEl.querySelector('#m-due-t').value || '23:59'}:00` : null,
          due_tz: ovEl.querySelector('#m-tz-zone')?.value || (S.settings.school_tz || 'America/New_York'),
          time_needed_min: +ovEl.querySelector('#m-need').dataset.min || 60,
        };
        t ? await Api.patch('/tasks/' + t.id, body) : await Api.post('/tasks', body);
        await loadAll();
        toast(t ? `updated \u00b7 ${body.title}` : `added task \u00b7 ${body.title}`);
      });
    // populate due date/time (zone-correct prefill) + location tz picker
    if (t?.due_at) {
      ov.querySelector('#m-due-d').value = Api.dayInZone(t.due_at, t.due_tz || S.settings.school_tz || 'America/New_York');
      ov.querySelector('#m-due-t').value = Api.fmtInZone(t.due_at, t.due_tz || S.settings.school_tz || 'America/New_York', { hour: '2-digit', minute: '2-digit', hour12: false });
    }
    initTzPicker(ov, t?.due_tz || S.settings.school_tz || 'America/New_York');
    wireStepper(ov.querySelector('#m-need'));
    ov.querySelector('#m-title').focus();
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
        toast(`${course ? 'updated' : 'added'} course \u00b7 ${nm}`);
      });
    wireSwatches($('modal-root'));
  }

  function activityModal(existing) {
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
        toast(`${existing ? 'updated' : 'blocked'} \u00b7 ${title}`);
      });
    wireSwatches(ov);
    for (const b of ov.querySelectorAll('.daypick button'))
      b.onclick = () => b.classList.toggle('sel');
  }

  function canvasModal() {
    modal(`
      <h2>canvas</h2>
      <p class="muted small">token: psu.instructure.com → Account → Settings → + New Access Token.
        Stored in your own database, used server-side only.</p>
      <div class="frow"><label>base url</label>
        <input id="m-url" value="${esc(S.canvas.base_url || 'https://psu.instructure.com')}" /></div>
      <div class="frow"><label>access token</label>
        <input id="m-tok" type="password" placeholder="${S.canvas.configured ? '•••••• (saved)' : 'paste token'}" /></div>
      ${ACTIONS('save')}`,
      async (act, ov) => {
        if (act !== 'save') return;
        const body = { canvas_base_url: ov.querySelector('#m-url').value.trim() };
        const tok = ov.querySelector('#m-tok').value.trim();
        if (tok) body.canvas_token = tok;
        await Api.put('/config/settings', body);
        await loadAll();
        toast('canvas saved — hit sync now');
      });
  }

  async function settingsModal() {
    const awake = await Api.get('/awake');
    const termCfg = await Api.get('/config/term');
    const t = termCfg.term || {};
    const aw = Object.fromEntries(awake.map((a) => [a.weekday, a]));
    modal(`
      <h2>settings</h2>
      <div class="frow">
        <div><label>min study block (min)</label>
          <input id="m-min" type="number" value="${S.settings.min_block_min}" /></div>
        <div><label>start ahead (days)</label>
          <input id="m-ahead" type="number" value="${S.settings.start_ahead_days}" /></div>
        <div><label>yellow at (% of need)</label>
          <input id="m-yel" type="number" value="${S.settings.yellow_threshold_pct}" /></div>
        <div><label>week starts on</label>
          <select id="m-wkstart">
            <option value="6" ${S.settings.week_start === 6 ? 'selected' : ''}>Sunday</option>
            <option value="0" ${S.settings.week_start === 0 ? 'selected' : ''}>Monday</option>
          </select></div>
      </div>
      <div class="frow"><label>term — classes start / end / exams end</label>
        <input id="m-ts" type="date" value="${t.classes_start || ''}" />
        <input id="m-te" type="date" value="${t.classes_end || ''}" />
        <input id="m-tx" type="date" value="${t.exam_end || ''}" />
      </div>
      <div class="frow"><label>awake time (study time can only exist inside)</label></div>
      ${DAYS.map((d, i) => `<div class="awake-row"><span class="muted">${d}</span>
        <input type="time" data-aws="${i}" value="${minToHM(aw[i]?.start_min ?? 480)}" />
        <input type="time" data-awe="${i}" value="${minToHM(aw[i]?.end_min ?? 1410)}" />
      </div>`).join('')}
      ${ACTIONS('save')}`,
      async (act, ov) => {
        if (act !== 'save') return;
        await Api.put('/config/settings', {
          min_block_min: +ov.querySelector('#m-min').value || 30,
          start_ahead_days: +ov.querySelector('#m-ahead').value || 3,
          yellow_threshold_pct: +ov.querySelector('#m-yel').value || 40,
          week_start: +ov.querySelector('#m-wkstart').value,
        });
        await Api.put('/config/term', {
          classes_start: ov.querySelector('#m-ts').value || null,
          classes_end: ov.querySelector('#m-te').value || null,
          exam_end: ov.querySelector('#m-tx').value || null,
        });
        await Api.put('/awake', DAYS.map((_, i) => ({
          weekday: i,
          start_min: hmToMin(ov.querySelector(`[data-aws="${i}"]`).value),
          end_min: hmToMin(ov.querySelector(`[data-awe="${i}"]`).value),
        })));
        await loadAll();
      });
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
