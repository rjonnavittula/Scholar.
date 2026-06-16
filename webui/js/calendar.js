/* calendar.js — FullCalendar v6 adapter for scholar.
   Keeps the exact Cal interface app.js expects: mount(el, S, H), render(), setView(view, n).
   Handlers: H.onPlan(taskId, dateIso, startMin, durMin),
             H.onMovePlanned(pid, dateIso, sMin, eMin),
             H.onBlockMenu(block).
   FullCalendar (global `FullCalendar`) handles week/day/month render + drag + resize. */
const Cal = (() => {
  let root, S, H, fc = null;
  let view = 'week';
  let nDays = 7;

  const tz = () => {
    const st = (S && S.settings) || {};
    return { home: st.home_tz || 'America/New_York', school: st.school_tz || 'America/New_York' };
  };
  const courseOf = (task) => S.courses.find((c) => c.id === task?.course_id);
  const taskOf = (id) => S.tasks.flatMap((t) => [t, ...(t.subtasks || [])]).find((x) => x.id === id);
  const hexA = (hex, a) => {
    const h = (hex || '#8A7F73').replace('#', '');
    const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  };
  const pad = (n) => String(n).padStart(2, '0');
  const minToHM = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const mins = (d) => d.getHours() * 60 + d.getMinutes();
  const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

  const VIEW_MAP = { day: 'timeGridDay', twoDay: 'timeGridTwoDay', week: 'timeGridWeek', month: 'dayGridMonth', nextN: 'timeGrid' };
  const fcView = () => VIEW_MAP[view] || 'timeGridWeek';

  function mount(el, state, handlers) { root = el; S = state; H = handlers; }

  function events() {
    const evs = [];
    for (const p of S.planned) {
      const t = taskOf(p.task_id) || {};
      const c = courseOf(t);
      const color = c?.color || '#8A7F73';
      evs.push({
        id: 'p' + p.id,
        title: t.title || 'study',
        start: p.start_at.slice(0, 19),
        end: (p.end_at || '').slice(0, 19) || undefined,
        editable: !p.completed,
        backgroundColor: hexA(color, 0.16),
        borderColor: hexA(color, 0.55),
        textColor: color,
        classNames: ['plan-ev', p.completed ? 'done' : ''],
        extendedProps: { kind: 'planned', pid: p.id, taskId: p.task_id },
      });
    }
    for (const act of S.activities) {
      const col = act.color || '#6F7F66';
      evs.push({
        groupId: 'act' + act.id,
        daysOfWeek: [(act.weekday + 1) % 7],
        startTime: minToHM(act.start_min),
        endTime: minToHM(act.end_min),
        display: 'block',
        title: act.title,
        backgroundColor: hexA(col, 0.2),
        borderColor: hexA(col, 0.85),
        textColor: col,
        editable: false,
        classNames: ['activity-ev'],
        extendedProps: { kind: 'activity', actId: act.id },
      });
    }
    for (const t of S.tasks.filter((x) => x.status !== 'done' && x.due_at)) {
      const lv = (S.cushionByTask[t.id] || {}).level;
      evs.push({
        id: 'd' + t.id,
        title: '\u2691 ' + (t.title || ''),
        start: t.due_at.slice(0, 19),
        editable: false,
        classNames: ['due-ev', lv === 'red' ? 'red' : (lv === 'yellow' ? 'yellow' : '')],
        backgroundColor: 'transparent',
        borderColor: 'transparent',
        textColor: lv === 'red' ? '#C66' : '#8A7F73',
        extendedProps: { kind: 'due', taskId: t.id },
      });
    }
    // passed-time shading: background events from midnight to now/end-of-day
    const now = new Date();
    const todayStr = isoDate(now);
    // shade a generous window around the current view; FC clips to visible range
    for (let off = -40; off <= 5; off++) {
      const d = new Date(now); d.setDate(d.getDate() + off);
      const ds = isoDate(d);
      if (ds > todayStr) continue;
      const endStr = (ds === todayStr)
        ? `${ds}T${pad(now.getHours())}:${pad(now.getMinutes())}:00`
        : `${ds}T23:59:59`;
      evs.push({
        start: `${ds}T00:00:00`, end: endStr,
        display: 'background', classNames: ['passed-bg'],
        backgroundColor: 'rgba(20,18,16,.45)',
        extendedProps: { kind: 'passed' },
      });
    }
    return evs;
  }

  function planDuration(taskId) {
    const t = taskOf(taskId);
    const rem = t ? Math.max(0, (t.time_needed_min || 60) - (t.time_spent_min || 0)) : 60;
    return Math.max(30, Math.min(rem || 60, 120));
  }

  function buildOptions() {
    const firstDay = S.settings.week_start === 0 ? 1 : 0;
    return {
      timeZone: 'local',
      initialView: fcView(),
      headerToolbar: false,
      firstDay,
      allDaySlot: false,
      nowIndicator: true,
      slotDuration: '00:30:00',
      snapDuration: '00:15:00',
      expandRows: true,
      height: '100%',
      editable: true,
      eventResizableFromStart: true,
      droppable: true,
      dayMaxEvents: true,
      views: { timeGrid: { type: 'timeGrid', duration: { days: nDays } },
               timeGridTwoDay: { type: 'timeGrid', duration: { days: 2 } } },
      events: events(),
      eventDrop: (info) => {
        const x = info.event.extendedProps;
        if (x.kind !== 'planned') { info.revert(); return; }
        const s = info.event.start, e = info.event.end || new Date(s.getTime() + 30 * 60000);
        H.onMovePlanned(x.pid, isoDate(s), mins(s), mins(e));
      },
      eventResize: (info) => {
        const x = info.event.extendedProps;
        if (x.kind !== 'planned') { info.revert(); return; }
        H.onMovePlanned(x.pid, isoDate(info.event.start), mins(info.event.start), mins(info.event.end));
      },
      eventClick: (info) => {
        const x = info.event.extendedProps;
        if (x.kind === 'planned') {
          const block = S.planned.find((p) => p.id === x.pid);
          if (block) H.onBlockMenu(block);
        } else if (x.kind === 'due' && H.onTaskEdit) {
          H.onTaskEdit(x.taskId);
        }
      },
      eventReceive: (info) => {
        const tid = info.event.extendedProps.dropTaskId;
        const s = info.event.start;
        const e = info.event.end || new Date(s.getTime() + planDuration(tid) * 60000);
        const dur = Math.round((e - s) / 60000) || planDuration(tid);
        info.event.remove();           // remove FC's temp event; reload shows the real one
        if (tid) H.onPlan(tid, isoDate(s), mins(s), dur);
      },
      eventDidMount: (info) => {
        if (info.event.extendedProps.kind === 'planned' && info.event.end && info.event.end < new Date())
          info.el.classList.add('passed');
      },
    };
  }

  function ensure() {
    if (!root) return;
    if (typeof FullCalendar === 'undefined') {
      root.innerHTML = '<div class="cal-fallback">calendar library failed to load \u2014 check your connection.</div>';
      return;
    }
    if (!fc) {
      fc = new FullCalendar.Calendar(root, buildOptions());
      fc.render();
      if (typeof ResizeObserver !== 'undefined') {
        let raf = null;
        const ro = new ResizeObserver(() => {
          if (raf) cancelAnimationFrame(raf);
          raf = requestAnimationFrame(() => fc && fc.updateSize());
        });
        ro.observe(root);
      }
    }
  }

  function render() {
    ensure();
    if (!fc) return;
    if (view === 'nextN') fc.setOption('views', { timeGrid: { type: 'timeGrid', duration: { days: nDays } } });
    fc.changeView(fcView());
    if (S.weekStart) fc.gotoDate(new Date(S.weekStart));
    fc.removeAllEvents();
    for (const e of events()) fc.addEvent(e);
  }

  function resize() { if (fc) fc.updateSize(); }

  function setView(v, n) {
    view = v;
    if (n) nDays = n;
    render();
  }

  return { mount, render, setView, resize };
})();
