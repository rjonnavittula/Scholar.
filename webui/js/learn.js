/* learn.js — Scholar Courses DB-backed UI.
   Vanilla frontend. Backend owns courses/modules/nodes/lessons.
   No raw model-generated HTML/JS. */
window.HiveCourses = (() => {
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  let state = null;
  let activeCategory = 'ALL COURSES';
  let activeTrackId = null;
  let activeTrack = null;
  let activeLessonRef = null;
  let activeLesson = null;

  const icons = {
    python: '</>', code: '</>', programming: '</>', cs: '</>', algorithm: '▦', data: '▦',
    ai: '◌', neural: '◌', math: '∞', hardware: '◎', circuit: '◎', exam: '◆',
    anatomy: '◇', biology: '◇', chemistry: '△', default: '◈'
  };

  function iconFor(title) {
    const t = String(title || '').toLowerCase();
    for (const [k, v] of Object.entries(icons)) if (t.includes(k)) return v;
    return icons.default;
  }

  function inputLabel(track) {
    const value = String(track?.input_type || 'source_text');
    if (value === 'system_prompt') return 'course prompt';
    if (value === 'source_text') return 'source text';
    return value.replace(/_/g, ' ');
  }

  function categoryFor(track) {
    const title = `${track?.title || ''} ${track?.role || ''}`.toLowerCase();
    if (/(python|code|programming|algorithm|software|developer|cs)/.test(title)) return 'PROGRAMMING';
    if (/(anatomy|medical|biology|physiology)/.test(title)) return 'MEDICAL';
    return 'GENERAL';
  }

  function categoriesFromTracks(tracks) {
    const cats = ['ALL COURSES'];
    for (const t of tracks || []) {
      const cat = categoryFor(t);
      if (!cats.includes(cat)) cats.push(cat);
    }
    return cats;
  }

  function currentTracks() {
    const tracks = state?.tracks || [];
    if (activeCategory === 'ALL COURSES') return tracks;
    return tracks.filter((t) => categoryFor(t) === activeCategory);
  }

  function setLoading(el, message = 'Loading course library…') {
    el.innerHTML = `<div class="forge-shell"><main class="forge-dashboard"><section class="forge-empty fade-in">
      <div class="forge-mark big"><span>S.</span></div><h3>${esc(message)}</h3>
      <p>Scholar is reading your saved courses from Postgres.</p>
    </section></main></div>`;
  }

  async function loadTracks(Api) {
    const tracks = await Api.get('/learn/tracks');
    state = { tracks, categories: categoriesFromTracks(tracks), loaded: true };
    if (!state.categories.includes(activeCategory)) activeCategory = 'ALL COURSES';
  }

  async function loadTrack(Api, trackId) {
    activeTrack = await Api.get(`/learn/tracks/${trackId}`);
    activeTrackId = String(activeTrack.id);
    return activeTrack;
  }

  async function loadLesson(Api, nodeId) {
    activeLesson = await Api.get(`/learn/nodes/${nodeId}/lesson`);
    return activeLesson;
  }

  async function render(el, S, Api) {
    try {
      if (!state) {
        setLoading(el);
        await loadTracks(Api);
      }
      if (activeLessonRef) {
        if (!activeLesson || String(activeLesson.node_id) !== String(activeLessonRef.nodeId)) {
          setLoading(el, 'Opening lesson draft…');
          await loadLesson(Api, activeLessonRef.nodeId);
        }
        return renderLesson(el, activeLesson, S, Api);
      }
      if (activeTrackId) {
        if (!activeTrack || String(activeTrack.id) !== String(activeTrackId)) {
          setLoading(el, 'Opening course map…');
          await loadTrack(Api, activeTrackId);
        }
        return renderTopology(el, activeTrack, S, Api);
      }
      renderDashboard(el, S, Api);
    } catch (e) {
      renderError(el, e, S, Api);
    }
  }

  function renderError(el, e, S, Api) {
    el.innerHTML = `<div class="forge-shell"><main class="forge-dashboard"><section class="forge-empty fade-in">
      <div class="forge-mark big"><span>!</span></div><h3>Course sync failed</h3>
      <p>${esc(e.message || e)}</p><button data-retry>Retry</button>
    </section></main></div>`;
    const b = el.querySelector('[data-retry]');
    if (b) b.onclick = () => { state = null; activeTrack = null; activeLesson = null; render(el, S, Api); };
  }

  function renderDashboard(el, S, Api) {
    const cats = state.categories || ['ALL COURSES'];
    const tracks = currentTracks();
    el.innerHTML = `<div class="forge-shell">
      <aside class="forge-sidebar">
        <div class="forge-mark"><span>S.</span></div>
        <h1>Course<br>Library</h1>
        <p class="forge-kicker">Saved Courses</p>
        <nav class="forge-disciplines">
          ${cats.map((cat) => `<button data-forge-cat="${esc(cat)}" class="${cat === activeCategory ? 'active' : ''}">${esc(cat)}</button>`).join('')}
        </nav>
        <button class="forge-new-discipline" data-forge-refresh>Refresh Library</button>
      </aside>
      <main class="forge-dashboard">
        <header class="forge-dash-head">
          <div><p>Library</p><h2>${esc(dashboardTitle())}</h2></div>
          <div class="forge-actions"><button data-forge-text-node>+ Create Course</button></div>
        </header>
        ${tracks.length ? renderTrackCards(tracks) : renderEmptyArchive()}
      </main>
      <div class="forge-modal-host"></div>
    </div>`;
    wireDashboard(el, S, Api);
  }

  function dashboardTitle() {
    return activeCategory === 'ALL COURSES' ? 'Scholar Courses' : `${activeCategory} Courses`;
  }

  function renderEmptyArchive() {
    return `<section class="forge-empty fade-in">
      <div class="forge-mark big"><span>S.</span></div>
      <h3>No Courses Yet</h3>
      <p>Paste a programming course prompt, syllabus, or notes. Scholar will create a saved course map in Postgres.</p>
      <button data-forge-text-node>Create Course</button>
    </section>`;
  }

  function renderTrackCards(tracks) {
    return `<div class="forge-course-grid">
      ${tracks.map((track, idx) => `<article class="forge-course-card" data-forge-track="${esc(track.id)}" style="--delay:${idx * 80}ms">
        <div><p>${esc(inputLabel(track))}</p><h3>${esc(track.title)}</h3></div>
        <div class="forge-card-modules">${modulePreview(track)}</div>
        <footer><span>${track.module_count ?? (track.modules || []).length} modules</span><span>${esc(track.status || 'draft')}</span></footer>
      </article>`).join('')}
    </div>`;
  }

  function modulePreview(track) {
    const titles = track.module_titles || (track.modules || []).map((m) => m.title);
    if (!titles.length) return '<span>Course map pending</span>';
    return titles.slice(0, 4).map((title) => `<span>${esc(title)}</span>`).join('');
  }

  function wireDashboard(el, S, Api) {
    el.querySelectorAll('[data-forge-cat]').forEach((b) => b.onclick = () => {
      activeCategory = b.dataset.forgeCat;
      activeTrackId = null; activeTrack = null; activeLessonRef = null; activeLesson = null;
      render(el, S, Api);
    });
    el.querySelectorAll('[data-forge-track]').forEach((b) => b.onclick = () => {
      activeTrackId = b.dataset.forgeTrack;
      activeTrack = null; activeLessonRef = null; activeLesson = null;
      render(el, S, Api);
    });
    el.querySelectorAll('[data-forge-text-node]').forEach((b) => b.onclick = () => openTextModal(el, S, Api));
    const refresh = el.querySelector('[data-forge-refresh]');
    if (refresh) refresh.onclick = async () => { state = null; await render(el, S, Api); };
  }

  function modalHost(el) { return el.querySelector('.forge-modal-host') || el; }

  function openTextModal(el, S, Api) {
    modalHost(el).innerHTML = `<div class="forge-modal modal-overlay fade-in"><div class="forge-modal-card">
      <h2>Create Course</h2>
      <p>Paste a programming course prompt, syllabus text, notes, or transcript. Scholar will parse it into a saved course map.</p>
      <textarea data-prompt-input placeholder="System Prompt
Role & Persona
You are the Python Mentor.

Module 1: Python Basics
Module 2: Functions
Module 3: Files and Modules
Module 4: Async Programming"></textarea>
      <div class="forge-modal-actions"><button data-close>Cancel</button><button data-save>Create Course</button></div>
    </div></div>`;
    const host = modalHost(el);
    host.querySelector('[data-close]').onclick = () => { host.innerHTML = ''; };
    host.querySelector('[data-save]').onclick = async () => {
      const text = host.querySelector('[data-prompt-input]').value || '';
      if (!text.trim()) return;
      const save = host.querySelector('[data-save]');
      save.disabled = true; save.textContent = 'Creating…';
      try {
        const track = await Api.post('/learn/tracks/from-source', { text });
        await loadTracks(Api);
        activeCategory = categoryFor(track);
        activeTrackId = String(track.id);
        activeTrack = track;
        activeLessonRef = null; activeLesson = null;
        render(el, S, Api);
      } catch (e) {
        save.disabled = false; save.textContent = 'Create Course';
        alert(e.message || e);
      }
    };
  }

  function renderTopology(el, track, S, Api) {
    if (!track) { activeTrackId = null; return render(el, S, Api); }
    const modules = track.modules || [];
    el.innerHTML = `<div class="forge-shell forge-map-shell">
      <aside class="forge-sidebar">
        <button class="forge-back" data-forge-back>← Courses</button>
        <div class="forge-mark"><span>S.</span></div>
        <h1>${esc(track.title)}</h1>
        <p class="forge-course-meta">${esc(inputLabel(track))} · ${modules.length} modules · ${esc(track.status || 'draft')}</p>
        <div class="forge-mastery"><span>${masteryForTrack(track)}%</span><em>mastery</em></div>
      </aside>
      <main class="forge-topology">
        <header class="forge-map-head"><p>${esc(categoryFor(track))}</p><h2>Course Map</h2></header>
        <div class="forge-map-stage">
          ${constellationSvg(modules)}
          ${modules.map((mod, i) => renderModuleNode(mod, i)).join('')}
        </div>
      </main>
    </div>`;
    el.querySelector('[data-forge-back]').onclick = () => { activeTrackId = null; activeTrack = null; render(el, S, Api); };
    el.querySelectorAll('[data-node]').forEach((b) => b.onclick = () => {
      const nodeId = b.dataset.node;
      const mod = modules.find((m) => (m.nodes || []).some((n) => String(n.id) === String(nodeId)));
      const node = mod && (mod.nodes || []).find((n) => String(n.id) === String(nodeId));
      if (!node || node.locked || mod.locked) return;
      activeLessonRef = { trackId: track.id, nodeId: node.id };
      activeLesson = null;
      render(el, S, Api);
    });
  }

  function masteryForTrack(track) {
    const mods = track.modules || [];
    if (!mods.length) return 0;
    const done = mods.filter((m) => m.completed).length;
    return Math.round((done / mods.length) * 100);
  }

  function constellationSvg(modules) {
    if (modules.length < 2) return '';
    let d = 'M 220 42 ';
    for (let i = 1; i < modules.length; i++) {
      if (modules[i].locked) break;
      const px = 220 + Math.sin((i - 1) * 1.5) * 92;
      const py = (i - 1) * 162 + 42;
      const cx = 220 + Math.sin(i * 1.5) * 92;
      const cy = i * 162 + 42;
      const my = py + (cy - py) / 2;
      d += ` C ${px} ${my}, ${cx} ${my}, ${cx} ${cy}`;
    }
    return `<svg class="forge-winding" style="height:${Math.max(260, modules.length * 162)}px" viewBox="0 0 440 ${Math.max(260, modules.length * 162)}" preserveAspectRatio="xMidYMin meet"><path d="${d}" /></svg>`;
  }

  function renderModuleNode(mod, i) {
    const firstNode = (mod.nodes || [])[0];
    const stateName = mod.completed ? 'completed' : mod.locked ? 'locked' : 'active';
    const nodeId = firstNode ? firstNode.id : '';
    const exp = firstNode?.exp ?? mod.exp ?? 50;
    const title = firstNode?.title || `${mod.title} Overview`;
    const x = Math.sin(i * 1.5) * 92;
    return `<button class="forge-node-row ${stateName}" data-node="${esc(nodeId)}" style="--x:${x}px; --delay:${i * 90}ms">
      <span class="forge-node-orb"><i>${esc(iconFor(mod.title))}</i></span>
      <span class="forge-node-card"><em>Module ${i + 1}</em><b>${esc(mod.title)}</b><small>${stateName.toUpperCase()} · ${esc(title)} · +${exp} EXP</small></span>
    </button>`;
  }

  function renderLesson(el, lesson, S, Api) {
    if (!lesson) { activeLessonRef = null; return render(el, S, Api); }
    el.innerHTML = `<div class="forge-lesson fade-in">
      <aside class="forge-lesson-side"><button data-exit>← Exit Lesson</button><p>Lesson Draft</p><h1>${esc(lesson.title)}</h1><div class="forge-scanner"><span></span></div></aside>
      <main class="forge-lesson-main">
        ${(lesson.blocks || []).map((b, i) => renderBlock(b, i)).join('')}
        <div class="forge-complete"><h2>Lesson Ready</h2><p>This draft is saved to Postgres. Completion, mastery, and source-grounded generation come next.</p><button data-complete>Return to Course Map</button></div>
      </main>
    </div>`;
    el.querySelector('[data-exit]').onclick = () => { activeLessonRef = null; activeLesson = null; render(el, S, Api); };
    el.querySelector('[data-complete]').onclick = () => { activeLessonRef = null; activeLesson = null; activeTrack = null; render(el, S, Api); };
  }

  function renderBlock(block, i) {
    const type = block.block_type || block.type || 'text';
    const payload = block.payload || {};
    const title = block.title || type.replace(/_/g, ' ');
    const delay = `--delay:${i * 120}ms`;
    if (type === 'definition') {
      return `<section class="forge-block slide-up" style="${delay}"><p>Definition</p><h2>${esc(title)}</h2><div class="forge-prose"><b>${esc(payload.term || title)}</b><br>${esc(payload.definition || payload.body || '')}</div></section>`;
    }
    if (type === 'recall_prompt') {
      return `<section class="forge-block slide-up" style="${delay}"><p>Recall Gate</p><h2>${esc(title)}</h2><div class="forge-prose">${esc(payload.prompt || payload.body || '')}</div></section>`;
    }
    if (type === 'quiz') {
      const options = payload.options || [];
      return `<section class="forge-block slide-up" style="${delay}"><p>Misconception Check</p><h2>${esc(title)}</h2><h3>${esc(payload.question || '')}</h3><div class="forge-options">${options.map((o, j) => `<button data-answer="${j}">${esc(o)}</button>`).join('')}</div></section>`;
    }
    if (type === 'ordered_relation' || type === 'diagram') {
      const items = payload.items || payload.steps || payload.labels || [];
      return `<section class="forge-block slide-up" style="${delay}"><p>${esc(type.replace(/_/g, ' '))}</p><h2>${esc(title)}</h2><div class="forge-safe-diagram">${items.map((x) => `<span>${esc(x.label || x)}</span>`).join('')}</div></section>`;
    }
    if (type === 'case') {
      return `<section class="forge-block slide-up" style="${delay}"><p>Case Node</p><h2>${esc(title)}</h2><div class="forge-prose">${esc(payload.scenario || payload.body || '')}</div></section>`;
    }
    if (type === 'source_quote') {
      return `<section class="forge-block slide-up" style="${delay}"><p>Source Quote</p><h2>${esc(title)}</h2><blockquote class="forge-prose">${esc(payload.quote || payload.body || '')}</blockquote></section>`;
    }
    if (type === 'code') {
      return `<section class="forge-block slide-up" style="${delay}"><p>Code Block</p><h2>${esc(title)}</h2><pre class="forge-prose"><code>${esc(payload.code || payload.body || '')}</code></pre></section>`;
    }
    return `<section class="forge-block slide-up" style="${delay}"><p>Lesson Block</p><h2>${esc(title)}</h2><div class="forge-prose">${esc(payload.body || payload.text || '')}</div></section>`;
  }

  return { render };
})();
