/* learn.js — HIVE-Courses v1.1.
   Brilliant-style focus + Boot.dev-style map + Shovel-style academic signals.
   Frontend-only: derives course missions from existing Scholar state. */
window.HiveCourses = (() => {
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const fmtDur = (mins) => {
    const m = Math.max(0, Math.round(Number(mins) || 0));
    const h = Math.floor(m / 60);
    const r = m % 60;
    return h && r ? `${h}h ${r}m` : h ? `${h}h` : `${r}m`;
  };

  const parseDate = (iso) => {
    if (!iso) return null;
    return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  };

  const daysUntil = (iso) => {
    const d = parseDate(iso);
    if (!d || Number.isNaN(d.getTime())) return null;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const due = new Date(d); due.setHours(0, 0, 0, 0);
    return Math.round((due - today) / 86400000);
  };

  const nodeMeta = (category) => ({
    Exam: ['Boss fight', 'Prove mastery under pressure', '◆'],
    Quiz: ['Checkpoint', 'Fast recall and concept precision', '◇'],
    Homework: ['Practice set', 'Build fluency through reps', '▣'],
    Lab: ['Lab node', 'Hands-on application', '⬢'],
    Project: ['Build node', 'Ship a larger artifact', '⬡'],
    Reading: ['Lore node', 'Turn material into usable concepts', '◌'],
    Discussion: ['Comms node', 'Explain your thinking clearly', '✦'],
    Other: ['Side quest', 'Finish the academic objective', '•'],
    '': ['Mission', 'Clarify and complete the next step', '•'],
  }[category || ''] || ['Side quest', 'Finish the academic objective', '•']);

  function tasksFor(S, course, includeDone = false) {
    const rows = (S.tasks || []).filter((t) => t.course_id === course.id);
    return includeDone ? rows : rows.filter((t) => t.status !== 'done');
  }

  function sortedOpenTasks(S, course) {
    return tasksFor(S, course).slice().sort((a, b) => {
      const ad = a.due_at || '9999';
      const bd = b.due_at || '9999';
      if (ad !== bd) return ad.localeCompare(bd);
      if (!!a.priority_flag !== !!b.priority_flag) return a.priority_flag ? -1 : 1;
      return String(a.title || '').localeCompare(String(b.title || ''));
    });
  }

  function courseSummary(S, course) {
    const all = tasksFor(S, course, true);
    const open = all.filter((t) => t.status !== 'done');
    const done = all.length - open.length;
    const dueSoon = open.filter((t) => {
      const d = daysUntil(t.due_at);
      return d != null && d >= 0 && d <= 7;
    });
    const overdue = open.filter((t) => {
      const d = daysUntil(t.due_at);
      return d != null && d < 0;
    });
    const workload = open.reduce((sum, t) => sum + Math.max(0, (t.time_needed_min || 0) - (t.time_spent_min || 0)), 0);
    const canvasTasks = open.filter((t) => t.source === 'canvas').length;
    const structuredCats = new Set(['Reading', 'Exam', 'Quiz', 'Homework', 'Project', 'Lab', 'Discussion']);
    const syllabusSignals = open.filter((t) => t.source !== 'canvas' && structuredCats.has(t.category || '')).length;
    const activities = (S.activities || []).filter((a) => a.course_id === course.id).length;
    const mastery = all.length ? Math.round((done / all.length) * 100) : 0;
    const pressure = overdue.length ? 'danger' : dueSoon.length ? 'hot' : open.length ? 'live' : 'calm';
    return { all, open, done, dueSoon, overdue, workload, canvasTasks, syllabusSignals, activities, mastery, pressure };
  }

  function statusForCourse(S, course) {
    const s = courseSummary(S, course);
    if (s.overdue.length) return ['danger', `${s.overdue.length} late`];
    if (s.dueSoon.length) return ['hot', `${s.dueSoon.length} due soon`];
    if (s.open.length) return ['live', `${s.open.length} open`];
    return ['calm', 'clear'];
  }

  function renderRoadmap(S) {
    const courses = S.courses || [];
    if (!courses.length) {
      return '<div class="learn-empty"><h3>No course paths yet.</h3><p class="muted">Add courses or import Canvas first. HIVE-Courses turns them into playable learning paths.</p></div>';
    }
    return courses.map((c, i) => {
      const [tone, label] = statusForCourse(S, c);
      const s = courseSummary(S, c);
      return `<button class="learn-path ${tone}" data-learn-course="${c.id}" style="--cc:${esc(c.color || '#8A7F73')}">
        <span class="lp-num">${String(i + 1).padStart(2, '0')}</span>
        <span class="lp-body"><b>${esc(c.name)}</b><em>${esc(label)} · ${fmtDur(s.workload)} workload</em></span>
        <span class="lp-ring"></span>
      </button>`;
    }).join('');
  }

  function missionNodes(S, course) {
    const tasks = sortedOpenTasks(S, course);
    if (!tasks.length) {
      return [
        { state: 'done', icon: '✓', label: 'Course created', sub: 'Ready for enrichment' },
        { state: 'current', icon: '✦', label: 'Generate path', sub: 'Local AI next patch' },
        { state: 'locked', icon: '◆', label: 'Boss quiz', sub: 'Unlock after lessons' },
      ];
    }
    const nodes = tasks.slice(0, 6).map((t, i) => {
      const d = daysUntil(t.due_at);
      const meta = nodeMeta(t.category);
      const late = d != null && d < 0;
      const urgent = d != null && d <= 2;
      return {
        task: t,
        state: late ? 'danger' : i === 0 ? 'current' : urgent ? 'hot' : 'open',
        icon: meta[2],
        label: t.title,
        sub: `${t.category || 'Task'} · ${d == null ? 'unscheduled' : d < 0 ? `${Math.abs(d)}d late` : d === 0 ? 'today' : `${d}d`}`,
      };
    });
    nodes.push({ state: 'locked', icon: '◆', label: 'Mastery check', sub: 'AI-generated boss node' });
    return nodes;
  }

  function nodeMapHtml(S, course) {
    return `<div class="learn-map" style="--cc:${esc(course.color || '#8A7F73')}">
      ${missionNodes(S, course).map((n, i) => `<button class="lm-node ${n.state}" data-node-idx="${i}" ${n.task ? `data-task-id="${n.task.id}"` : ''}>
        <span class="lm-glyph">${esc(n.icon)}</span>
        <span class="lm-copy"><b>${esc(n.label)}</b><em>${esc(n.sub)}</em></span>
      </button>`).join('')}
    </div>`;
  }

  function learningSourcesHtml(S, course) {
    const s = courseSummary(S, course);
    const canvasLinked = course.source === 'canvas' || s.canvasTasks > 0 || (S.canvas && (S.canvas.configured || S.canvas.ics_configured));
    const items = [
      ['Canvas', canvasLinked ? `${s.canvasTasks || 0} task signal${s.canvasTasks === 1 ? '' : 's'}` : 'not linked yet', canvasLinked],
      ['Syllabus', s.syllabusSignals ? `${s.syllabusSignals} structured deadline${s.syllabusSignals === 1 ? '' : 's'}` : 'import PDF/text', !!s.syllabusSignals],
      ['Lecture rhythm', s.activities ? `${s.activities} class block${s.activities === 1 ? '' : 's'}` : 'add lecture activities', !!s.activities],
      ['Slides/notes', 'next: upload lecture material', false],
    ];
    return `<div class="mission-sources">${items.map(([k, v, on]) => `<span class="ms-item ${on ? 'on' : ''}"><b>${esc(k)}</b><em>${esc(v)}</em></span>`).join('')}</div>`;
  }

  function missionPanelHtml(S, Api, course) {
    const s = courseSummary(S, course);
    const next = sortedOpenTasks(S, course)[0];
    const meta = next ? nodeMeta(next.category) : nodeMeta('');
    const schoolTz = (S.settings && S.settings.school_tz) || 'America/New_York';
    const due = next && next.due_at ? Api.dayInZone(next.due_at, schoolTz) : 'no due date';
    return `<aside class="mission-panel">
      <div class="mission-kicker">next mission</div>
      <h3>${next ? esc(next.title) : 'Build this path'}</h3>
      <p>${next ? esc(meta[1]) : 'This course has no open tasks. Add Canvas work, syllabus deadlines, or slides to generate lessons.'}</p>
      <div class="mission-facts">
        <span><b>${next ? esc(next.category || 'Task') : 'Path'}</b><em>type</em></span>
        <span><b>${next ? esc(due) : 'ready'}</b><em>deadline</em></span>
        <span><b>${next ? fmtDur(Math.max(0, (next.time_needed_min || 0) - (next.time_spent_min || 0))) : fmtDur(s.workload)}</b><em>remaining</em></span>
      </div>
      ${learningSourcesHtml(S, course)}
      <button class="learn-start" disabled>Start interactive lesson · next patch</button>
      <p class="learn-note">v1.1 is visual only. v2 wires local Ollama to turn Canvas tasks, syllabus items, and lecture slides into playable lessons.</p>
    </aside>`;
  }

  function heroHtml(S, course) {
    const s = courseSummary(S, course);
    const [tone, label] = statusForCourse(S, course);
    return `<section class="course-hero ${tone}" style="--cc:${esc(course.color || '#8A7F73')}">
      <div class="course-orbit"><span>✦</span><i></i><i></i><i></i></div>
      <div class="course-copy">
        <div class="lesson-kicker">${esc(course.source === 'canvas' ? 'Canvas path' : 'Scholar path')} · ${esc(label)}</div>
        <h2>${esc(course.name)}</h2>
        <p>${course.notes ? esc(course.notes) : 'A playable learning route generated from the academic signals Scholar already tracks.'}</p>
      </div>
      <div class="mastery-ring" style="--pct:${s.mastery * 3.6}deg"><b>${s.mastery}%</b><em>task mastery</em></div>
    </section>`;
  }

  function statHudHtml(S) {
    const courses = S.courses || [];
    const open = (S.tasks || []).filter((t) => t.status !== 'done');
    const totalWork = open.reduce((sum, t) => sum + Math.max(0, (t.time_needed_min || 0) - (t.time_spent_min || 0)), 0);
    const dueSoon = open.filter((t) => { const d = daysUntil(t.due_at); return d != null && d >= 0 && d <= 7; }).length;
    const streak = S.streak && (S.streak.current || S.streak.current_days || S.streak.streak || 0);
    const xp = Math.max(0, ((S.tasks || []).filter((t) => t.status === 'done').length * 25) + ((S.planned || []).filter((p) => p.completed).length * 10));
    return `<div class="learn-stats game-hud">
      <span><b>${courses.length}</b><em>paths</em></span>
      <span><b>${dueSoon}</b><em>due soon</em></span>
      <span><b>${fmtDur(totalWork)}</b><em>workload</em></span>
      <span><b>${xp}</b><em>scholar xp</em></span>
      <span><b>${streak || 0}</b><em>streak</em></span>
    </div>`;
  }

  function emptyCanvas() {
    return `<section class="lesson-canvas idle">
      <div class="lesson-orb">✦</div>
      <h2>Pick a course path.</h2>
      <p class="muted">The learning map will convert Canvas deadlines, syllabus items, lecture rhythms, and later slide uploads into playable missions.</p>
    </section>`;
  }

  function lessonCanvas(S, Api, course) {
    if (!course) return emptyCanvas();
    return `<section class="lesson-canvas v11" style="--cc:${esc(course.color || '#8A7F73')}">
      ${heroHtml(S, course)}
      <div class="learn-playfield">
        <div class="map-wrap">
          <div class="map-title"><span>learning map</span><em>from Scholar signals</em></div>
          ${nodeMapHtml(S, course)}
        </div>
        ${missionPanelHtml(S, Api, course)}
      </div>
    </section>`;
  }

  function render(el, S, Api) {
    const courses = S.courses || [];
    const selectedId = Number(localStorage.getItem('hive_courses_selected') || (courses[0] && courses[0].id) || 0);
    const selected = courses.find((c) => c.id === selectedId) || courses[0] || null;

    el.innerHTML = `<div class="learn-shell v11-shell">
      <header class="learn-head v11-head">
        <div><div class="learn-eyebrow">local-first learning layer</div><h1>HIVE-Courses</h1>
          <p>Brilliant-style focus. Boot.dev-style path progression. Shovel-style academic planning underneath.</p></div>
        ${statHudHtml(S)}
      </header>
      <div class="learn-body v11-body">
        <aside class="learn-roadmap">
          <div class="learn-rh"><span>Course paths</span><em>Canvas · syllabus · manual</em></div>
          ${renderRoadmap(S)}
        </aside>
        <div class="learn-main">${lessonCanvas(S, Api, selected)}</div>
      </div>
    </div>`;

    for (const b of el.querySelectorAll('[data-learn-course]')) {
      b.classList.toggle('active', selected && +b.dataset.learnCourse === selected.id);
      b.onclick = () => {
        localStorage.setItem('hive_courses_selected', b.dataset.learnCourse);
        render(el, S, Api);
      };
    }
  }

  return { render };
})();
