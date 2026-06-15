/* panel.js — the right rail: Overdue / Due buckets / No due date. */
function SCHOOL_TZ() { return (window.__S && window.__S.settings && window.__S.settings.school_tz) || 'America/New_York'; }
const Panel = (() => {
  let root, S, H, query = '';

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmtDur = (m) => { m = Math.abs(m);
    return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m` : `${m}m`; };

  function mount(el, state, handlers) {
    root = el; S = state; H = handlers;
    document.getElementById('task-search').addEventListener('input', (e) => {
      query = e.target.value.toLowerCase(); render();
    });
  }

  function bucketLabel(dueIso, todayIso) {
    if (dueIso === todayIso) return 'Due: Today';
    const d = new Date(dueIso + 'T00:00');
    const t = new Date(todayIso + 'T00:00');
    const diff = Math.round((d - t) / 86400000);
    if (diff === 1) return 'Due: Tomorrow';
    if (diff < 7) return 'Due: ' + d.toLocaleDateString(undefined, { weekday: 'long' });
    return 'Later';
  }

  function render() {
    const now = new Date();
    const todayIso = S.todayIso;
    const open = S.tasks.filter((t) => t.status !== 'done'
      && (!query || t.title.toLowerCase().includes(query)));

    const groups = [];
    const overdue = open.filter((t) => t.due_at && new Date(t.due_at) < now);
    const noDue = open.filter((t) => !t.due_at);
    if (overdue.length) groups.push({ name: '🔥 Overdue', cls: 'red', items: overdue });

    const future = open.filter((t) => t.due_at && new Date(t.due_at) >= now)
      .sort((a, b) => a.due_at.localeCompare(b.due_at));
    const byLabel = {};
    for (const t of future) {
      const lab = bucketLabel(Api.dayInZone(t.due_at, SCHOOL_TZ()), todayIso);
      (byLabel[lab] ??= []).push(t);
    }
    for (const [lab, items] of Object.entries(byLabel)) groups.push({ name: lab, items });
    if (noDue.length) groups.push({ name: 'No due date', items: noDue });

    root.innerHTML = groups.map((g) => `
      <div class="tgroup">
        <div class="tgroup-head ${g.cls || ''}">${g.name}
          <span class="ct">${g.items.length}</span></div>
        ${g.items.map(card).join('')}
      </div>`).join('') || '<p class="muted small">no tasks — add one, or sync Canvas.</p>';

    wire();
  }

  function card(t) {
    const c = S.courses.find((x) => x.id === t.course_id);
    const cu = S.cushionByTask[t.id];
    const rem = Math.max(0, t.time_needed_min - t.time_spent_min);
    const plannedMin = (S.planned || []).filter((b) => b.task_id === t.id)
      .reduce((a, b) => a + Math.round((new Date(b.end_at) - new Date(b.start_at)) / 60000), 0);
    const need = t.time_needed_min || 0;
    const planLbl = plannedMin > 0 ? `${Math.round(plannedMin/60*10)/10}h of ${Math.round(need/60*10)/10}h planned` : '';
    const subs = t.subtasks || [];
    const subLbl = subs.length ? `\u2611 ${subs.filter((x)=>x.status==='done').length}/${subs.length} subtasks` : '';
    return `<div class="tcard" draggable="true" data-tid="${t.id}">
        <button class="plan-btn" data-plan="${t.id}" title="plan into next free slot">plan</button>
      <div class="row-actions">
        <button data-act="flag" title="priority">${t.priority_flag ? '⚑' : '⚐'}</button>
        <button data-act="edit" title="edit">✎</button>
        <button data-act="done" title="done">✓</button>
        <button data-act="del" title="delete">✕</button>
      </div>
      ${c ? `<div class="course" style="color:${c.color}">
              <span class="dot" style="background:${c.color}"></span>${esc(c.name)}</div>` : ''}
      <div class="title">${t.priority_flag ? '<span class="flagged">⚑</span> ' : ''}${esc(t.title)}</div>
      <div class="meta">
        ${t.category ? `<span>${esc(t.category)}</span>` : ''}
        ${t.due_at ? `<span>due ${Api.fmtInZone(t.due_at, SCHOOL_TZ(), { month: '2-digit', day: '2-digit' })} ${Api.fmtInZone(t.due_at, SCHOOL_TZ(), { hour: '2-digit', minute: '2-digit', hour12: false })}</span>` : ''}
        <span>need ${fmtDur(rem)}</span>
        ${cu ? `<span class="cushion ${cu.level}">cushion ${cu.cushion_min < 0 ? '−' : ''}${fmtDur(cu.cushion_min)}</span>` : ''}
      </div>
    </div>`;
  }

  function wire() {
    for (const el of root.querySelectorAll('.tcard')) {
      const tid = +el.dataset.tid;
      el.addEventListener('dragstart', (e) => {
        window._dragTaskId = tid;
        e.dataTransfer.setData('text/task', String(tid));
        e.dataTransfer.effectAllowed = 'copy';
      });
      el.addEventListener('dragend', () => { window._dragTaskId = 0; });
      for (const btn of el.querySelectorAll('[data-act]')) {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          H.onTaskAction(btn.dataset.act, tid);
        });
      }
      const pb = el.querySelector('[data-plan]');
      if (pb) pb.addEventListener('click', (e) => {
        e.stopPropagation();
        if (H.onPlanQuick) H.onPlanQuick(+pb.dataset.plan);
      });
      // click the card body -> open edit (ignore clicks on buttons/controls)
      el.addEventListener('click', (e) => {
        if (e.target.closest('button, [data-act], [data-plan], input, a')) return;
        if (H.onTaskEdit) H.onTaskEdit(tid);
      });
    }
  }

  return { mount, render };
})();
