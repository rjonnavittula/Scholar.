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
  let activeSources = null;
  let activeSourcesTrackId = null;

  function activateCourseWorkspace(el) {
    if (el) el.classList.add('forge-active');
    const body = document.body;
    const rightToggle = document.getElementById('collapse-right');
    if (body && !body.classList.contains('no-right')) {
      body.classList.add('no-right');
      if (rightToggle) rightToggle.textContent = '‹';
      window.dispatchEvent(new Event('resize'));
    }
  }

  const icons = {
    python: 'Py', javascript: 'JS', typescript: 'TS', react: '⚛', node: 'JS',
    code: '</>', programming: '</>', cs: '</>', algorithm: 'ALG', data: 'DB',
    ai: 'AI', neural: 'AI', math: '∞', hardware: 'HW', circuit: '⚡', exam: '◆',
    anatomy: 'AN', biology: 'BIO', chemistry: 'CH', default: '◈'
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
    activeSources = null;
    activeSourcesTrackId = null;
    return activeTrack;
  }

  async function loadTrackSources(Api, trackId) {
    activeSources = await Api.get(`/learn/tracks/${trackId}/sources`);
    activeSourcesTrackId = String(trackId);
    return activeSources;
  }

  async function loadLesson(Api, nodeId) {
    const started = await Api.post(`/learn/nodes/${nodeId}/start`, {});
    if (started?.track) activeTrack = started.track;
    activeLesson = started?.lesson || await Api.get(`/learn/nodes/${nodeId}/lesson`);
    return activeLesson;
  }

  async function render(el, S, Api) {
    activateCourseWorkspace(el);
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
        if (!activeSources || String(activeSourcesTrackId) !== String(activeTrackId)) {
          await loadTrackSources(Api, activeTrackId);
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
        <div class="forge-context-mark"><span>☰</span></div>
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
      ${tracks.map((track, idx) => {
        const total = track.module_count ?? (track.modules || []).length;
        const done = track.completed_module_count ?? 0;
        const mastery = Math.round((track.mastery || 0) * 100);
        return `<article class="forge-course-card" data-forge-track="${esc(track.id)}" style="--delay:${idx * 80}ms">
          <div class="forge-card-top"><span class="forge-course-glyph">${esc(iconFor(track.title + ' ' + (track.role || '')))}</span><p>${esc(inputLabel(track))}</p></div>
          <h3>${esc(track.title)}</h3>
          <div class="forge-card-modules">${modulePreview(track)}</div>
          ${track.next_module_title ? `<small class="forge-next-course">Next: ${esc(track.next_module_title)}</small>` : '<small class="forge-next-course">Course complete</small>'}
          <div class="forge-course-progress" aria-label="${mastery}% mastery"><i style="width:${mastery}%"></i></div>
          <footer><span>${done}/${total} modules</span><span>${mastery}% mastery</span></footer>
        </article>`;
      }).join('')}
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
      activeTrackId = null; activeTrack = null; activeSources = null; activeSourcesTrackId = null; activeLessonRef = null; activeLesson = null;
      render(el, S, Api);
    });
    el.querySelectorAll('[data-forge-track]').forEach((b) => b.onclick = () => {
      activeTrackId = b.dataset.forgeTrack;
      activeTrack = null; activeSources = null; activeSourcesTrackId = null; activeLessonRef = null; activeLesson = null;
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
        activeSources = null; activeSourcesTrackId = null;
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
        <div class="forge-context-mark course"><span>${esc(iconFor(track.title + ' ' + (track.role || '')))}</span></div>
        <h1>${esc(track.title)}</h1>
        <p class="forge-course-meta">${esc(inputLabel(track))} · ${modules.length} modules · ${esc(track.status || 'draft')}</p>
        <div class="forge-mastery"><span>${masteryForTrack(track)}%</span><em>mastery</em></div>
        ${renderSourcePanel(activeSources || [])}
        <div class="forge-side-actions">
          <button data-forge-source class="forge-source-add">+ Add Source</button>
          <button data-forge-delete class="forge-danger">Delete Course</button>
        </div>
      </aside>
      <main class="forge-topology">
        <header class="forge-map-head"><p>${esc(categoryFor(track))}</p><h2>Course Map</h2></header>
        <div class="forge-map-stage">
          ${constellationSvg(modules)}
          ${modules.map((mod, i) => renderModuleNode(mod, i)).join('')}
        </div>
      </main>
      <div class="forge-modal-host"></div>
    </div>`;
    el.querySelector('[data-forge-back]').onclick = () => { activeTrackId = null; activeTrack = null; activeSources = null; activeSourcesTrackId = null; render(el, S, Api); };
    const addSource = el.querySelector('[data-forge-source]');
    if (addSource) addSource.onclick = () => openSourceModal(el, S, Api, track);
    const del = el.querySelector('[data-forge-delete]');
    if (del) del.onclick = async () => {
      if (!confirm(`Delete ${track.title}? This removes the saved course map and lesson drafts.`)) return;
      del.disabled = true; del.textContent = 'Deleting…';
      try {
        await Api.del(`/learn/tracks/${track.id}`);
        activeTrackId = null; activeTrack = null; activeSources = null; activeSourcesTrackId = null; activeLessonRef = null; activeLesson = null; state = null;
        await loadTracks(Api);
        render(el, S, Api);
      } catch (e) {
        del.disabled = false; del.textContent = 'Delete Course';
        alert(e.message || e);
      }
    };
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

  function renderSourcePanel(sources) {
    const count = sources.length;
    return `<section class="forge-source-panel">
      <div class="forge-source-head"><span>${count}</span><em>${count === 1 ? 'source' : 'sources'}</em></div>
      ${count ? `<div class="forge-source-list">${sources.slice(0, 4).map(renderSourceChip).join('')}</div>` : '<p>No trusted sources linked yet.</p>'}
    </section>`;
  }

  function renderSourceChip(src) {
    const label = src.role || src.trust_level || 'source';
    return `<div class="forge-source-chip"><b>${esc(src.title)}</b><small>${esc(label)} · ${esc(src.source_type)} · ${Number(src.char_count || 0)} chars</small></div>`;
  }

  async function openSourceModal(el, S, Api, track) {
    const host = modalHost(el);
    host.innerHTML = `<div class="forge-modal modal-overlay fade-in"><div class="forge-modal-card forge-source-modal">
      <h2>Add Source</h2>
      <p>Register trusted course material first. Parsing, chunking, RAG, and lesson generation come after this registry layer.</p>
      <label>Title<input data-source-title placeholder="Python Basics Notes"></label>
      <div class="forge-source-row">
        <label>Type<select data-source-type><option value="markdown">Markdown</option><option value="text">Text</option><option value="syllabus">Syllabus</option><option value="transcript">Transcript</option></select></label>
        <label>Trust<select data-source-trust><option value="user">User</option><option value="official">Official</option><option value="instructor">Instructor</option><option value="reference">Reference</option></select></label>
      </div>
      <textarea data-source-body placeholder="# Python Basics\nVariables store references. Functions package reusable behavior."></textarea>
      <div class="forge-source-existing"><h3>Source Registry</h3><div data-source-registry><p>Loading sources…</p></div></div>
      <div class="forge-modal-actions"><button data-close>Cancel</button><button data-save>Create & Link</button></div>
    </div></div>`;
    host.querySelector('[data-close]').onclick = () => { host.innerHTML = ''; };
    const registry = host.querySelector('[data-source-registry]');
    try {
      const sources = await Api.get('/learn/sources');
      registry.innerHTML = sources.length ? sources.map((src) => `<button class="forge-source-registry-item" data-link-source="${esc(src.id)}"><b>${esc(src.title)}</b><small>${esc(src.source_type)} · ${esc(src.trust_level)} · ${Number(src.char_count || 0)} chars</small></button>`).join('') : '<p>No sources registered yet.</p>';
      registry.querySelectorAll('[data-link-source]').forEach((b) => b.onclick = async () => {
        b.disabled = true;
        try {
          await Api.post(`/learn/tracks/${track.id}/sources/${b.dataset.linkSource}`, { role: 'supplemental' });
          activeSources = null; activeSourcesTrackId = null;
          await loadTrackSources(Api, track.id);
          host.innerHTML = '';
          render(el, S, Api);
        } catch (e) { b.disabled = false; alert(e.message || e); }
      });
    } catch (e) {
      registry.innerHTML = `<p>${esc(e.message || e)}</p>`;
    }
    host.querySelector('[data-save]').onclick = async () => {
      const title = host.querySelector('[data-source-title]').value.trim();
      const body = host.querySelector('[data-source-body]').value.trim();
      if (!title || !body) return alert('Add a source title and body.');
      const save = host.querySelector('[data-save]');
      save.disabled = true; save.textContent = 'Linking…';
      try {
        const source = await Api.post('/learn/sources', {
          title,
          source_type: host.querySelector('[data-source-type]').value,
          trust_level: host.querySelector('[data-source-trust]').value,
          body_text: body,
          metadata: { origin: 'course-map-ui' }
        });
        await Api.post(`/learn/tracks/${track.id}/sources/${source.id}`, { role: 'primary' });
        activeSources = null; activeSourcesTrackId = null;
        await loadTrackSources(Api, track.id);
        host.innerHTML = '';
        render(el, S, Api);
      } catch (e) {
        save.disabled = false; save.textContent = 'Create & Link';
        alert(e.message || e);
      }
    };
  }

  function masteryForTrack(track) {
    const mods = track.modules || [];
    if (!mods.length) return 0;
    const done = mods.filter((m) => m.completed).length;
    return Math.round((done / mods.length) * 100);
  }

  function moduleOffset(i) {
    return Math.round(Math.sin(i * 1.35) * 86);
  }

  function moduleY(i) {
    return 72 + i * 188;
  }

  function pathForPoints(points) {
    if (!points.length) return '';
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const cur = points[i];
      const mid = prev.y + (cur.y - prev.y) / 2;
      d += ` C ${prev.x} ${mid}, ${cur.x} ${mid}, ${cur.x} ${cur.y}`;
    }
    return d;
  }

  function constellationSvg(modules) {
    if (modules.length < 2) return '';
    const h = Math.max(320, modules.length * 188 + 90);
    const points = modules.map((_, i) => ({ x: 220 + moduleOffset(i), y: moduleY(i) }));
    const active = points.filter((_, i) => !modules[i].locked || i === 0);
    return `<svg class="forge-winding" style="height:${h}px" viewBox="0 0 440 ${h}" preserveAspectRatio="xMidYMin meet">
      <path class="ghost" d="${pathForPoints(points)}" />
      <path class="live" d="${pathForPoints(active)}" />
    </svg>`;
  }

  function renderModuleNode(mod, i) {
    const firstNode = (mod.nodes || [])[0];
    const nodeDone = !!firstNode?.completed;
    const stateName = mod.completed || nodeDone ? 'completed' : mod.locked ? 'locked' : 'active';
    const nodeId = firstNode ? firstNode.id : '';
    const exp = firstNode?.exp ?? mod.exp ?? 50;
    const title = firstNode?.title || `${mod.title} Overview`;
    const x = moduleOffset(i);
    const locked = stateName === 'locked';
    const hint = locked ? 'Complete previous module' : stateName === 'completed' ? 'Completed' : 'Ready to study';
    return `<button class="forge-node-row ${stateName}" data-node="${esc(nodeId)}" style="--x:${x}px; --delay:${i * 90}ms" ${locked ? 'disabled aria-disabled="true"' : ''}>
      <span class="forge-node-orb"><i>${esc(iconFor(mod.title))}</i></span>
      <span class="forge-node-card"><em>Module ${i + 1} · ${esc(hint)}</em><b>${esc(mod.title)}</b><small>${stateName.toUpperCase()} · ${esc(title)} · ${Math.round((firstNode?.mastery || mod.mastery || 0) * 100)}% mastery · +${exp} EXP</small></span>
    </button>`;
  }

  function renderLesson(el, lesson, S, Api) {
    if (!lesson) { activeLessonRef = null; return render(el, S, Api); }
    const completed = lesson.status === 'completed';
    el.innerHTML = `<div class="forge-lesson fade-in">
      <aside class="forge-lesson-side"><button data-exit>← Exit Lesson</button><p>${completed ? 'Completed Lesson' : 'Lesson Draft'}</p><h1>${esc(lesson.title)}</h1><div class="forge-lesson-mini"><span>${completed ? 'Saved' : 'Interactive shell'}</span><em>${esc(lesson.estimated_min || 10)} min</em></div></aside>
      <main class="forge-lesson-main">
        ${(lesson.blocks || []).map((b, i) => renderBlock(b, i)).join('')}
        <div class="forge-complete"><h2>${completed ? 'Lesson Complete' : 'Mark Progress'}</h2><p>${completed ? 'This lesson is completed and saved to Postgres.' : 'Mark this lesson complete to update mastery, unlock the next module, and return to the course map.'}</p><button data-complete>${completed ? 'Return to Course Map' : 'Complete Lesson'}</button></div>
      </main>
    </div>`;
    el.querySelector('[data-exit]').onclick = () => { activeLessonRef = null; activeLesson = null; render(el, S, Api); };
    el.querySelector('[data-complete]').onclick = async () => {
      if (completed) { activeLessonRef = null; activeLesson = null; render(el, S, Api); return; }
      const btn = el.querySelector('[data-complete]');
      btn.disabled = true; btn.textContent = 'Saving…';
      try {
        const result = await Api.post(`/learn/nodes/${activeLessonRef.nodeId}/complete`, { mastery: 1.0 });
        if (result?.track) { activeTrack = result.track; activeTrackId = String(result.track.id); }
        activeLessonRef = null; activeLesson = null; state = null;
        await loadTracks(Api);
        render(el, S, Api);
      } catch (e) {
        btn.disabled = false; btn.textContent = 'Complete Lesson';
        alert(e.message || e);
      }
    };
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
      return `<section class="forge-block interactive slide-up" style="${delay}"><p>Recall Gate</p><h2>${esc(title)}</h2><div class="forge-prose">${esc(payload.prompt || payload.body || '')}</div><textarea class="forge-recall-input" placeholder="Type your recall here before revealing the explanation. Persistence comes in the interaction phase."></textarea></section>`;
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
