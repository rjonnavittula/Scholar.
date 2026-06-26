/* learn.js — HIVE-Courses Forge replacement.
   Scholar Forge UI transplanted into Scholar's existing vanilla frontend.
   No React CDN/Babel/Tailwind. No model-generated HTML/JS nodes. */
window.HiveCourses = (() => {
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const STORE = 'hive_courses_forge_v1';
  let state = null;
  let activeCategory = null;
  let activeCourseId = null;
  let activeLesson = null;

  const icons = {
    anatomy: '◇', biology: '◇', cell: '◇', neuro: '◇', chemistry: '△', law: '⚖', history: '▥',
    art: '✧', design: '✧', security: '▣', ai: '◌', neural: '◌', data: '▦', math: '∞',
    hardware: '◎', circuit: '◎', code: '</>', exam: '◆', default: '◈'
  };

  function loadStore() {
    try { return JSON.parse(localStorage.getItem(STORE) || '{}'); } catch { return {}; }
  }
  function saveStore() { localStorage.setItem(STORE, JSON.stringify(state)); }

  function uid(prefix = 'f') {
    return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
  }

  function iconFor(title) {
    const t = String(title || '').toLowerCase();
    for (const [k, v] of Object.entries(icons)) if (t.includes(k)) return v;
    return icons.default;
  }

  function xpFor(i, title) {
    const t = String(title || '').toLowerCase();
    if (t.includes('exam') || t.includes('mastery') || t.includes('clinical')) return 160;
    if (t.includes('case') || t.includes('lab') || t.includes('project')) return 120;
    return 80 + (i % 3) * 20;
  }

  function normalizeTitle(s) {
    return String(s || '').replace(/^[-*#\s]+/, '').replace(/[:：]\s*$/, '').trim();
  }

  function classifyInput(text) {
    const t = String(text || '');
    const hits = [
      /system prompt/i, /^#\s*system prompt/im, /##\s*role/im, /##\s*teaching style/im,
      /##\s*output format/im, /##\s*quiz mode/im, /core teaching philosophy/i,
      /interaction rules/i, /curriculum/i
    ].filter((rx) => rx.test(t)).length;
    return hits >= 2 ? 'system_prompt' : 'source_text';
  }

  function titleFromPrompt(text, category) {
    const lines = String(text || '').split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
    const role = lines.find((l) => /^#+\s*system prompt\s*:/i.test(l));
    if (role) return normalizeTitle(role.replace(/^#+\s*system prompt\s*:\s*/i, '')).replace(/^The\s+/i, '');
    const named = lines.find((l) => /^#\s+/.test(l));
    if (named) return normalizeTitle(named.replace(/^#+\s*/, '')).replace(/^System Prompt:\s*/i, '');
    const anatomy = lines.find((l) => /anatom/i.test(l));
    if (anatomy) return 'Anatomy Track';
    return `${category || 'Scholar'} Forge Track`;
  }

  function extractModules(text) {
    const src = String(text || '').replace(/\r/g, '');
    const lines = src.split('\n');
    const modules = [];
    const seen = new Set();
    const add = (title, source = '') => {
      title = normalizeTitle(title);
      title = title.replace(/^module\s*\d+\s*[:.)-]?\s*/i, '')
        .replace(/^chapter\s*\d+\s*[:.)-]?\s*/i, '')
        .replace(/^unit\s*\d+\s*[:.)-]?\s*/i, '')
        .replace(/^phase\s*\d+\s*[:.)-]?\s*/i, '');
      if (!title || title.length < 3) return;
      const key = title.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      modules.push({ id: uid('node'), title, exp: xpFor(modules.length, title), locked: modules.length > 0, completed: false, source });
    };

    for (const line of lines) {
      let m = line.match(/^\s*(?:#{1,3}\s*)?(?:module|chapter|unit|phase)\s+(\d+|[ivx]+)\s*[:.)-]\s*(.+)$/i);
      if (m) { add(m[2], line); continue; }
      m = line.match(/^\s*[-*]\s*(?:module|chapter|unit)\s+(\d+|[ivx]+)\s*[:.)-]\s*(.+)$/i);
      if (m) { add(m[2], line); continue; }
    }

    if (modules.length < 3) {
      for (const line of lines) {
        const m = line.match(/^\s*[-*]\s+([A-Za-z][A-Za-z0-9 ,/&()'-]{8,80})\s*$/);
        if (m && !/^(do not|never|always|when|use|ask|give|avoid)\b/i.test(m[1])) add(m[1], line);
        if (modules.length >= 10) break;
      }
    }

    if (!modules.length) {
      ['Orientation', 'Core Concepts', 'Spatial Map', 'Guided Practice', 'Clinical/Application Check', 'Mastery Review']
        .forEach((x) => add(x, 'fallback'));
    }

    return modules.slice(0, 12).map((m, i) => ({ ...m, locked: i > 0 }));
  }

  function buildCourseFromText(text, category) {
    const inputType = classifyInput(text);
    const title = titleFromPrompt(text, category);
    const modules = extractModules(text);
    return {
      id: uid('course'),
      title,
      category,
      inputType,
      rawPrompt: String(text || ''),
      createdAt: new Date().toISOString(),
      modules,
      mastery: 0,
    };
  }

  function initState(S) {
    const stored = loadStore();
    state = stored.categories ? stored : { categories: ['ANATOMY'], courses: { ANATOMY: [] } };
    for (const c of (S.courses || [])) {
      const cat = 'SCHOLAR';
      if (!state.categories.includes(cat)) state.categories.push(cat);
      if (!state.courses[cat]) state.courses[cat] = [];
      if (!state.courses[cat].some((x) => x.scholarCourseId === c.id)) {
        state.courses[cat].push({
          id: uid('course'), scholarCourseId: c.id, title: c.name, category: cat, inputType: 'scholar_course',
          createdAt: new Date().toISOString(), rawPrompt: c.notes || '', mastery: 0,
          modules: forgeModulesFromScholar(S, c),
        });
      }
    }
    activeCategory = activeCategory && state.categories.includes(activeCategory) ? activeCategory : state.categories[0];
    saveStore();
  }

  function forgeModulesFromScholar(S, c) {
    const tasks = (S.tasks || []).filter((t) => t.course_id === c.id).slice(0, 10);
    const base = tasks.length ? tasks.map((t, i) => ({
      id: uid('node'), title: t.title || `Mission ${i + 1}`, exp: xpFor(i, t.title), locked: i > 0, completed: t.status === 'done', source: t.category || 'Scholar task'
    })) : ['Course Orientation', 'Next Mission', 'Practice Node', 'Mastery Check'].map((x, i) => ({ id: uid('node'), title: x, exp: xpFor(i, x), locked: i > 0, completed: false, source: 'Scholar' }));
    return base;
  }

  function currentCourses() { return (state.courses[activeCategory] || []); }

  function render(el, S, Api) {
    initState(S || {});
    if (activeLesson) return renderLesson(el, activeLesson, S, Api);
    if (activeCourseId) return renderTopology(el, activeCourse(), S, Api);
    renderDashboard(el, S, Api);
  }

  function activeCourse() {
    for (const cat of state.categories) {
      const c = (state.courses[cat] || []).find((x) => x.id === activeCourseId);
      if (c) return c;
    }
    return null;
  }

  function renderDashboard(el, S, Api) {
    const cats = state.categories;
    const courses = currentCourses();
    el.innerHTML = `<div class="forge-shell">
      <aside class="forge-sidebar">
        <div class="forge-mark"><span>S.</span></div>
        <h1>Neural<br>Archives</h1>
        <p class="forge-kicker">Core Disciplines</p>
        <nav class="forge-disciplines">
          ${cats.map((cat) => `<button data-forge-cat="${esc(cat)}" class="${cat === activeCategory ? 'active' : ''}">${esc(cat)}</button>`).join('')}
        </nav>
        <button class="forge-new-discipline" data-forge-new-discipline>+ New Discipline</button>
      </aside>
      <main class="forge-dashboard">
        <header class="forge-dash-head">
          <div><p>Category</p><h2>${esc(activeCategory)} Topology</h2></div>
          <div class="forge-actions">
            <button data-forge-text-node>+ Text Node</button>
            <button data-forge-reset>Reset Local Forge</button>
          </div>
        </header>
        ${courses.length ? renderCourseCards(courses) : renderEmptyArchive()}
      </main>
      <div class="forge-modal-host"></div>
    </div>`;
    wireDashboard(el, S, Api);
  }

  function renderEmptyArchive() {
    return `<section class="forge-empty fade-in">
      <div class="forge-mark big"><span>S.</span></div>
      <h3>Neural Archives Uninitialized</h3>
      <p>The topology is empty. Paste a syllabus, notes, or a complete system prompt to establish this domain of study.</p>
      <button data-forge-text-node>Initialize Canvas</button>
    </section>`;
  }

  function renderCourseCards(courses) {
    return `<div class="forge-course-grid">
      ${courses.map((course, idx) => `<article class="forge-course-card" data-forge-course="${esc(course.id)}" style="--delay:${idx * 80}ms">
        <div><p>${esc(course.inputType === 'system_prompt' ? 'System Prompt Track' : course.inputType === 'scholar_course' ? 'Scholar Course' : 'Text Node')}</p>
        <h3>${esc(course.title)}</h3></div>
        <footer><span>${course.modules.length} modules</span><span>${course.mastery || 0}% mastery</span></footer>
      </article>`).join('')}
    </div>`;
  }

  function wireDashboard(el, S, Api) {
    el.querySelectorAll('[data-forge-cat]').forEach((b) => b.onclick = () => { activeCategory = b.dataset.forgeCat; activeCourseId = null; render(el, S, Api); });
    el.querySelectorAll('[data-forge-course]').forEach((b) => b.onclick = () => { activeCourseId = b.dataset.forgeCourse; render(el, S, Api); });
    el.querySelectorAll('[data-forge-text-node]').forEach((b) => b.onclick = () => openTextModal(el, S, Api));
    const nd = el.querySelector('[data-forge-new-discipline]');
    if (nd) nd.onclick = () => openDisciplineModal(el, S, Api);
    const reset = el.querySelector('[data-forge-reset]');
    if (reset) reset.onclick = () => { if (confirm('Reset local Forge tracks? Scholar courses remain in Scholar.')) { localStorage.removeItem(STORE); state = null; activeCategory = null; activeCourseId = null; render(el, S, Api); } };
  }

  function modalHost(el) { return el.querySelector('.forge-modal-host') || el; }

  function openDisciplineModal(el, S, Api) {
    modalHost(el).innerHTML = `<div class="forge-modal modal-overlay fade-in"><div class="forge-modal-card small">
      <h2>Define New Discipline</h2>
      <input data-discipline-input placeholder="e.g., PHYSIOLOGY" autofocus>
      <div class="forge-modal-actions"><button data-close>Abort</button><button data-save>Establish</button></div>
    </div></div>`;
    const host = modalHost(el);
    host.querySelector('[data-close]').onclick = () => { host.innerHTML = ''; };
    host.querySelector('[data-save]').onclick = () => {
      const val = (host.querySelector('[data-discipline-input]').value || '').trim().toUpperCase();
      if (!val) return;
      if (!state.categories.includes(val)) state.categories.push(val);
      state.courses[val] ||= [];
      activeCategory = val;
      saveStore(); render(el, S, Api);
    };
  }

  function openTextModal(el, S, Api) {
    modalHost(el).innerHTML = `<div class="forge-modal modal-overlay fade-in"><div class="forge-modal-card">
      <h2>Text Ingestion Node</h2>
      <p>Paste syllabus text, notes, or a complete system prompt. Forge will parse the topology deterministically.</p>
      <textarea data-prompt-input placeholder="Paste Anatomy system prompt here..."></textarea>
      <div class="forge-modal-actions"><button data-close>Abort</button><button data-save>Synthesize</button></div>
    </div></div>`;
    const host = modalHost(el);
    host.querySelector('[data-close]').onclick = () => { host.innerHTML = ''; };
    host.querySelector('[data-save]').onclick = () => {
      const text = host.querySelector('[data-prompt-input]').value || '';
      if (!text.trim()) return;
      const course = buildCourseFromText(text, activeCategory);
      state.courses[activeCategory] ||= [];
      state.courses[activeCategory].push(course);
      activeCourseId = course.id;
      saveStore(); render(el, S, Api);
    };
  }

  function renderTopology(el, course, S, Api) {
    if (!course) { activeCourseId = null; return renderDashboard(el, S, Api); }
    const nodes = course.modules || [];
    el.innerHTML = `<div class="forge-shell forge-map-shell">
      <aside class="forge-sidebar">
        <button class="forge-back" data-forge-back>← Archives</button>
        <div class="forge-mark"><span>S.</span></div>
        <h1>${esc(course.title)}</h1>
        <p class="forge-course-meta">${esc(course.inputType.replace('_', ' '))} · ${nodes.length} modules</p>
        <div class="forge-mastery"><span>${course.mastery || 0}%</span><em>mastery</em></div>
      </aside>
      <main class="forge-topology">
        <header class="forge-map-head"><p>${esc(course.category)}</p><h2>Course Topography</h2></header>
        <div class="forge-map-stage">
          ${constellationSvg(nodes)}
          ${nodes.map((node, i) => renderNode(node, i)).join('')}
        </div>
      </main>
    </div>`;
    el.querySelector('[data-forge-back]').onclick = () => { activeCourseId = null; render(el, S, Api); };
    el.querySelectorAll('[data-node]').forEach((b) => b.onclick = () => {
      const node = nodes.find((n) => n.id === b.dataset.node);
      if (!node || node.locked) return;
      activeLesson = { courseId: course.id, nodeId: node.id };
      render(el, S, Api);
    });
  }

  function constellationSvg(nodes) {
    if (nodes.length < 2) return '';
    let d = 'M 220 42 ';
    for (let i = 1; i < nodes.length; i++) {
      if (nodes[i].locked) break;
      const px = 220 + Math.sin((i - 1) * 1.5) * 92;
      const py = (i - 1) * 162 + 42;
      const cx = 220 + Math.sin(i * 1.5) * 92;
      const cy = i * 162 + 42;
      const my = py + (cy - py) / 2;
      d += ` C ${px} ${my}, ${cx} ${my}, ${cx} ${cy}`;
    }
    return `<svg class="forge-winding" style="height:${Math.max(260, nodes.length * 162)}px" viewBox="0 0 440 ${Math.max(260, nodes.length * 162)}" preserveAspectRatio="xMidYMin meet"><path d="${d}" /></svg>`;
  }

  function renderNode(node, i) {
    const x = Math.sin(i * 1.5) * 92;
    const state = node.completed ? 'completed' : node.locked ? 'locked' : 'active';
    return `<button class="forge-node-row ${state}" data-node="${esc(node.id)}" style="--x:${x}px; --delay:${i * 90}ms">
      <span class="forge-node-orb"><i>${esc(iconFor(node.title))}</i></span>
      <span class="forge-node-card"><em>Module ${i + 1}</em><b>${esc(node.title)}</b><small>${node.locked ? 'LOCKED' : node.completed ? 'COMPLETED' : 'ACTIVE'} · +${node.exp} EXP</small></span>
    </button>`;
  }

  function renderLesson(el, lessonRef, S, Api) {
    const course = activeCourse();
    const node = course && course.modules.find((n) => n.id === lessonRef.nodeId);
    if (!course || !node) { activeLesson = null; return render(el, S, Api); }
    const blocks = lessonBlocks(course, node);
    el.innerHTML = `<div class="forge-lesson fade-in">
      <aside class="forge-lesson-side"><button data-exit>← Exit Lesson</button><p>Active Node</p><h1>${esc(node.title)}</h1><div class="forge-scanner"><span></span></div></aside>
      <main class="forge-lesson-main">
        ${blocks.map((b, i) => renderBlock(b, i)).join('')}
        <div class="forge-complete"><h2>Node Ready</h2><p>Complete this module to unlock the next branch in the topology.</p><button data-complete>Synchronize & Return</button></div>
      </main>
    </div>`;
    el.querySelector('[data-exit]').onclick = () => { activeLesson = null; render(el, S, Api); };
    el.querySelector('[data-complete]').onclick = () => {
      node.completed = true;
      const idx = course.modules.findIndex((n) => n.id === node.id);
      if (course.modules[idx + 1]) course.modules[idx + 1].locked = false;
      const done = course.modules.filter((n) => n.completed).length;
      course.mastery = Math.round((done / course.modules.length) * 100);
      activeLesson = null; saveStore(); render(el, S, Api);
    };
  }

  function lessonBlocks(course, node) {
    const system = course.inputType === 'system_prompt';
    return [
      { type: 'text', title: 'Orientation', body: system ? `Use the track rules from the pasted system prompt. Start by orienting ${node.title} before memorizing details.` : `Build a first-principles model of ${node.title}.` },
      { type: 'diagram', title: 'Spatial Reconstruction', items: ['Where is it?', 'What is superficial/deep?', 'What is medial/lateral?', 'What passes through or around it?'] },
      { type: 'quiz', title: 'Recall Gate', question: `Explain ${node.title} in one clean mental model before moving on.`, options: ['Orientation first', 'Random memorization', 'Skip relations'], answer: 0 }
    ];
  }

  function renderBlock(b, i) {
    if (b.type === 'diagram') return `<section class="forge-block slide-up" style="--delay:${i * 120}ms"><p>Diagram Node</p><h2>${esc(b.title)}</h2><div class="forge-safe-diagram">${b.items.map((x) => `<span>${esc(x)}</span>`).join('')}</div></section>`;
    if (b.type === 'quiz') return `<section class="forge-block slide-up" style="--delay:${i * 120}ms"><p>Misconception Check</p><h2>${esc(b.title)}</h2><h3>${esc(b.question)}</h3><div class="forge-options">${b.options.map((o, j) => `<button data-answer="${j}">${esc(o)}</button>`).join('')}</div></section>`;
    return `<section class="forge-block slide-up" style="--delay:${i * 120}ms"><p>Lesson Block</p><h2>${esc(b.title)}</h2><div class="forge-prose">${esc(b.body)}</div></section>`;
  }

  return { render };
})();
