/* tutor.js — Phase 1 conversational tutor mode: setup + streaming chat UI.
   Self-contained IIFE module (same pattern as calendar.js/panel.js). Reads
   the API key straight from localStorage for the one raw streaming fetch
   this needs — api.js's Api object never exposes the key itself, only a
   fetch-then-json() wrapper unsuited to a streamed response body. */
window.HiveTutor = (() => {
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function renderMarkdownLite(text) {
    const parts = String(text ?? '').split(/```([\s\S]*?)```/);
    return parts.map((part, i) => {
      if (i % 2 === 1) {
        const lines = part.split('\n');
        if (lines[0] && /^[a-zA-Z0-9_+-]*$/.test(lines[0].trim()) && lines.length > 1) lines.shift();
        return `<pre class="tutor-code"><code>${esc(lines.join('\n'))}</code></pre>`;
      }
      return esc(part).replace(/\n/g, '<br>');
    }).join('');
  }

  function modalHost(el) { return el.querySelector('.forge-modal-host') || el; }

  function bubble(msg) {
    const role = msg.role === 'user' ? 'user' : 'assistant';
    return `<div class="tutor-bubble tutor-bubble-${role}" data-msg-id="${esc(msg.id || '')}">
      <div class="tutor-bubble-content">${renderMarkdownLite(msg.content)}</div>
    </div>`;
  }

  function openSetupModal(el, S, Api, track, onEnabled) {
    const host = modalHost(el);
    host.innerHTML = `<div class="forge-modal modal-overlay fade-in"><div class="forge-modal-card motion-pop">
      <h2>Set Up a Tutor</h2>
      <p>Give ${esc(track.title)} a conversational tutor — paste a system prompt, pick a preset, or describe what you want and let scholar draft one.</p>
      <div class="seg tutor-setup-seg">
        <span data-tab="preset" class="on">Presets</span>
        <span data-tab="describe">Describe it</span>
        <span data-tab="paste">Paste a prompt</span>
      </div>
      <div class="tutor-setup-panel" data-panel="preset">
        <div data-preset-list class="muted small">loading…</div>
      </div>
      <div class="tutor-setup-panel" data-panel="describe" hidden>
        <textarea data-describe-input placeholder="e.g. direct and technical, no fluff, teaches by having me write code myself and reviewing it line by line"></textarea>
        <button type="button" data-describe-gen class="ghost">generate a prompt</button>
      </div>
      <div class="tutor-setup-panel" data-panel="paste" hidden>
        <textarea data-paste-input placeholder="Paste a full tutor system prompt…"></textarea>
      </div>
      <div class="tutor-setup-review" data-review hidden>
        <label>Review &amp; edit before saving</label>
        <textarea data-final-prompt></textarea>
      </div>
      <div class="forge-modal-actions"><button data-close>Cancel</button><button data-save class="motion-button" disabled>Enable Tutor</button></div>
    </div></div>`;

    const close = () => { host.innerHTML = ''; };
    host.querySelector('[data-close]').onclick = close;

    const show = (name) => {
      host.querySelectorAll('.tutor-setup-seg span').forEach((s) => s.classList.toggle('on', s.dataset.tab === name));
      host.querySelectorAll('.tutor-setup-panel').forEach((p) => { p.hidden = p.dataset.panel !== name; });
    };
    host.querySelectorAll('.tutor-setup-seg span').forEach((s) => { s.onclick = () => show(s.dataset.tab); });

    const finalPromptEl = host.querySelector('[data-final-prompt]');
    const reviewEl = host.querySelector('[data-review]');
    const saveBtn = host.querySelector('[data-save]');
    const setFinal = (text) => {
      finalPromptEl.value = text || '';
      reviewEl.hidden = !finalPromptEl.value.trim();
      saveBtn.disabled = !finalPromptEl.value.trim();
    };
    finalPromptEl.oninput = () => { saveBtn.disabled = !finalPromptEl.value.trim(); };

    Api.get('/learn/tutor/presets').then((presets) => {
      host.querySelector('[data-preset-list]').innerHTML = presets.map((p) => `
        <button type="button" class="tutor-preset-card" data-preset="${esc(p.id)}">
          <b>${esc(p.label)}</b><span>${esc(p.blurb)}</span>
        </button>`).join('');
      host.querySelectorAll('[data-preset]').forEach((b) => b.onclick = () => {
        const preset = presets.find((p) => p.id === b.dataset.preset);
        if (preset) setFinal(preset.system_prompt);
        host.querySelectorAll('[data-preset]').forEach((o) => o.classList.toggle('sel', o === b));
      });
    }).catch(() => { host.querySelector('[data-preset-list]').textContent = 'could not load presets'; });

    host.querySelector('[data-paste-input]').oninput = (e) => setFinal(e.target.value);

    host.querySelector('[data-describe-gen]').onclick = async (e) => {
      const btn = e.currentTarget;
      const describe = host.querySelector('[data-describe-input]').value.trim();
      if (!describe) return;
      btn.disabled = true; btn.textContent = 'generating…'; btn.classList.add('is-loading');
      try {
        const result = await Api.post(`/learn/tracks/${track.id}/tutor/generate-prompt`, { describe });
        setFinal(result.system_prompt);
      } catch (err) {
        alert(err.message || err);
      } finally {
        btn.disabled = false; btn.textContent = 'generate a prompt'; btn.classList.remove('is-loading');
      }
    };

    saveBtn.onclick = async () => {
      const system_prompt = finalPromptEl.value.trim();
      if (!system_prompt) return;
      saveBtn.disabled = true; saveBtn.textContent = 'Saving…';
      try {
        await Api.post(`/learn/tracks/${track.id}/tutor/enable`, { system_prompt });
        close();
        onEnabled();
      } catch (err) {
        saveBtn.disabled = false; saveBtn.textContent = 'Enable Tutor';
        alert(err.message || err);
      }
    };
  }

  function studyPanelSection(track) {
    return `<section class="forge-memory-card tutor-panel-card">
      <div class="forge-memory-head"><span>Tutor</span></div>
      ${track.tutor_enabled
        ? `<p>A conversational tutor is set up for this course.</p>
           <div class="forge-memory-actions">
             <button data-tutor-open class="forge-index-action">Open chat</button>
             <button data-tutor-reconfigure class="forge-index-action">Reconfigure</button>
           </div>`
        : `<p>Add a conversational tutor to this course — paste a system prompt, pick a preset, or describe what you want.</p>
           <div class="forge-memory-actions"><button data-tutor-setup class="forge-index-action">Set up a tutor</button></div>`}
    </section>`;
  }

  function wireStudyPanelSection(el, S, Api, track, onOpen) {
    const setupBtn = el.querySelector('[data-tutor-setup]');
    if (setupBtn) setupBtn.onclick = () => openSetupModal(el, S, Api, track, onOpen);
    const reconfigBtn = el.querySelector('[data-tutor-reconfigure]');
    if (reconfigBtn) reconfigBtn.onclick = () => openSetupModal(el, S, Api, track, onOpen);
    const openBtn = el.querySelector('[data-tutor-open]');
    if (openBtn) openBtn.onclick = () => onOpen(true);
  }

  async function renderChat(el, track, Api, onExit) {
    el.innerHTML = `<div class="tutor-shell fade-in">
      <header class="tutor-topbar">
        <button data-tutor-exit class="forge-lesson-exit" aria-label="Exit tutor">×</button>
        <div class="tutor-topbar-title"><span>Tutor</span><h2>${esc(track.title)}</h2></div>
        <button data-tutor-clear class="ghost xs">clear conversation</button>
      </header>
      <main class="tutor-thread" data-tutor-thread><p class="muted small">loading…</p></main>
      <footer class="tutor-composer">
        <textarea data-tutor-input placeholder="Ask a question, paste code, say what you're stuck on…" rows="2"></textarea>
        <button data-tutor-send class="primary">send</button>
      </footer>
    </div>`;

    el.querySelector('[data-tutor-exit]').onclick = () => onExit();

    const threadEl = el.querySelector('[data-tutor-thread]');
    const input = el.querySelector('[data-tutor-input]');
    const sendBtn = el.querySelector('[data-tutor-send]');

    async function loadHistory() {
      const messages = await Api.get(`/learn/tracks/${track.id}/tutor/messages`);
      const visible = messages.filter((m) => m.role === 'user' || m.role === 'assistant');
      threadEl.innerHTML = visible.length ? visible.map(bubble).join('') : '<p class="muted small">Say hello to start.</p>';
      threadEl.scrollTop = threadEl.scrollHeight;
    }

    el.querySelector('[data-tutor-clear]').onclick = async () => {
      if (!confirm('Clear this tutor conversation? This cannot be undone.')) return;
      await Api.del(`/learn/tracks/${track.id}/tutor/messages`);
      loadHistory();
    };

    async function send() {
      const text = input.value.trim();
      if (!text || sendBtn.disabled) return;
      input.value = '';
      sendBtn.disabled = true;
      if (threadEl.querySelector('.muted.small')) threadEl.innerHTML = '';
      threadEl.insertAdjacentHTML('beforeend', bubble({ role: 'user', content: text }));
      const liveId = 'live-' + Date.now();
      threadEl.insertAdjacentHTML('beforeend', `<div class="tutor-bubble tutor-bubble-assistant" data-msg-id="${liveId}"><div class="tutor-bubble-content"></div></div>`);
      threadEl.scrollTop = threadEl.scrollHeight;
      const contentEl = threadEl.querySelector(`[data-msg-id="${liveId}"] .tutor-bubble-content`);
      let raw = '';

      try {
        const resp = await fetch(`/learn/tracks/${track.id}/tutor/messages`, {
          method: 'POST',
          headers: { 'X-API-Key': localStorage.getItem('hive-key') || '', 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: text }),
        });
        if (!resp.ok || !resp.body) throw new Error('tutor request failed (' + resp.status + ')');
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, idx).trim();
            buffer = buffer.slice(idx + 1);
            if (!line) continue;
            let event;
            try { event = JSON.parse(line); } catch (e) { continue; }
            if (event.type === 'text_delta') {
              raw += event.content;
              contentEl.innerHTML = renderMarkdownLite(raw);
              threadEl.scrollTop = threadEl.scrollHeight;
            } else if (event.type === 'error') {
              contentEl.innerHTML += `<p class="tutor-error">could not reply: ${esc(event.content)}</p>`;
            }
          }
        }
      } catch (err) {
        contentEl.innerHTML += `<p class="tutor-error">${esc(err.message || err)}</p>`;
      } finally {
        sendBtn.disabled = false;
        input.focus();
      }
    }

    sendBtn.onclick = send;
    input.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };

    await loadHistory();
    input.focus();
  }

  return { studyPanelSection, wireStudyPanelSection, renderChat, openSetupModal };
})();
