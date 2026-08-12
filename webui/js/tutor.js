/* tutor.js — Phase 1 conversational tutor mode: setup + streaming chat UI.
   Self-contained IIFE module (same pattern as calendar.js/panel.js). Reads
   the API key straight from localStorage for the one raw streaming fetch
   this needs — api.js's Api object never exposes the key itself, only a
   fetch-then-json() wrapper unsuited to a streamed response body. */
window.HiveTutor = (() => {
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // Inline markdown - bold/italic/inline-code/links - applied to text
  // that's ALREADY html-escaped (so it's safe to build tags around it
  // without a second escaping pass mangling the entity references).
  function renderInline(escapedText) {
    const codeSpans = [];
    let s = escapedText.replace(/`([^`\n]+)`/g, (_, code) => {
      codeSpans.push(code);
      return `\u0000${codeSpans.length - 1}\u0000`;
    });

    s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (_, label, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`);

    s = s.replace(/\*\*([^\n]+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__([^\n]+?)__/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/(^|[^_])_([^_\n]+?)_(?!_)/g, '$1<em>$2</em>');

    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codeSpans[Number(i)]}</code>`);
  }

  // Block markdown - headers, bulleted/numbered lists, paragraphs - for a
  // chunk of text known NOT to contain a fenced code block (those are
  // split out and handled separately in renderMarkdownLite, verbatim).
  function renderBlock(text) {
    const out = [];
    let listType = null;
    const closeList = () => { if (listType) { out.push(`</${listType}>`); listType = null; } };

    for (const rawLine of text.split('\n')) {
      const headerMatch = /^(#{1,6})\s+(.*)$/.exec(rawLine);
      const ulMatch = /^[-*]\s+(.*)$/.exec(rawLine);
      const olMatch = /^\d+\.\s+(.*)$/.exec(rawLine);

      if (headerMatch) {
        closeList();
        const level = Math.min(headerMatch[1].length + 2, 6); // never h1/h2 - too large inside a chat bubble
        out.push(`<h${level}>${renderInline(esc(headerMatch[2]))}</h${level}>`);
      } else if (ulMatch) {
        if (listType !== 'ul') { closeList(); out.push('<ul>'); listType = 'ul'; }
        out.push(`<li>${renderInline(esc(ulMatch[1]))}</li>`);
      } else if (olMatch) {
        if (listType !== 'ol') { closeList(); out.push('<ol>'); listType = 'ol'; }
        out.push(`<li>${renderInline(esc(olMatch[1]))}</li>`);
      } else {
        closeList();
        out.push(rawLine.trim() === '' ? '<br>' : renderInline(esc(rawLine)) + '<br>');
      }
    }
    closeList();
    return out.join('');
  }

  function renderMarkdownLite(text) {
    const parts = String(text ?? '').split(/```([\s\S]*?)```/);
    return parts.map((part, i) => {
      if (i % 2 === 1) {
        const lines = part.split('\n');
        if (lines[0] && /^[a-zA-Z0-9_+-]*$/.test(lines[0].trim()) && lines.length > 1) lines.shift();
        return `<pre class="tutor-code"><code>${esc(lines.join('\n'))}</code></pre>`;
      }
      return renderBlock(part);
    }).join('');
  }

  function modalHost(el) { return el.querySelector('.forge-modal-host') || el; }

  // Media (plot images, animation videos) lives behind the same X-API-Key
  // auth as everything else, so a plain <img src="..."> / <video src="...">
  // can't load it - the browser never attaches custom headers to those
  // requests. Instead the tag gets a data-media-url and this fetches it
  // with the header, then swaps in a blob: URL the element CAN load bare.
  function mediaTagHtml(url, kind) {
    if (!url) return '';
    if (kind === 'text/html' || /\.html($|\?)/i.test(url)) {
      // No allow-same-origin: the framed doc gets a unique opaque origin no
      // matter that it's served from this app's own domain - it genuinely
      // cannot reach this page's cookies, localStorage, or DOM.
      return `<iframe class="tutor-tool-media tutor-tool-interactive" data-media-url="${esc(url)}" sandbox="allow-scripts" title="interactive visual"></iframe>`;
    }
    const isVideo = (kind && kind.startsWith('video/')) || /\.mp4($|\?)/i.test(url);
    return isVideo
      ? `<video class="tutor-tool-media" data-media-url="${esc(url)}" controls></video>`
      : `<img class="tutor-tool-media" data-media-url="${esc(url)}" alt="rendered visual">`;
  }

  async function hydrateMedia(root) {
    const els = root.querySelectorAll('[data-media-url]');
    for (const el of els) {
      const url = el.getAttribute('data-media-url');
      if (!url || el.getAttribute('src') || el.getAttribute('srcdoc')) continue;
      try {
        const resp = await fetch(url, { headers: { 'X-API-Key': localStorage.getItem('hive-key') || '' } });
        if (!resp.ok) continue;
        if (el.tagName === 'IFRAME') {
          el.srcdoc = await resp.text();
        } else {
          const blob = await resp.blob();
          el.src = URL.createObjectURL(blob);
        }
      } catch (e) { /* leave unhydrated - not fatal, rest of the bubble still renders */ }
    }
  }

  function bubble(msg) {
    const role = msg.role === 'user' ? 'user' : 'assistant';
    return `<div class="tutor-bubble tutor-bubble-${role}" data-msg-id="${esc(msg.id || '')}">
      <div class="tutor-bubble-content">${renderMarkdownLite(msg.content)}</div>
    </div>`;
  }

  // "🔧 running…" placeholder shown the instant a tool_call event arrives,
  // before its tool_result has come back yet.
  function toolCallPendingBubble(id, name, args) {
    const code = (args && args.code) || '';
    if (name === 'define_tool') {
      const toolName = (args && args.name) || '?';
      return `<div class="tutor-bubble tutor-tool-bubble tutor-tool-pending" data-tool-id="${esc(id)}">
        <div class="tutor-tool-head"><span class="tutor-tool-spin">⚙</span> defining a new tool: <code>${esc(toolName)}</code>…</div>
        ${code ? `<pre class="tutor-code">${esc(code)}</pre>` : ''}
      </div>`;
    }
    return `<div class="tutor-bubble tutor-tool-bubble tutor-tool-pending" data-tool-id="${esc(id)}">
      <div class="tutor-tool-head"><span class="tutor-tool-spin">⚙</span> running <code>${esc(name)}</code>…</div>
      ${code ? `<pre class="tutor-code">${esc(code)}</pre>` : ''}
    </div>`;
  }

  // Replaces the pending bubble once the live tool_result event arrives —
  // has structured stdout/stderr/exit_code, so it can show pass/fail state.
  function toolResultBubbleHtml(id, evt) {
    const ok = evt.exit_code === 0 && !evt.timed_out;
    const status = evt.timed_out ? 'timed out' : (ok ? 'ok' : `exit ${evt.exit_code}`);
    const out = [evt.stdout, evt.stderr].filter(Boolean).join('\n');
    const head = evt.name === 'define_tool'
      ? `🔧 defining a new tool — ${esc(status)}`
      : `🔧 <code>${esc(evt.name)}</code> — ${esc(status)}`;
    return `<div class="tutor-bubble tutor-tool-bubble ${ok ? 'tutor-tool-ok' : 'tutor-tool-err'}" data-tool-id="${esc(id)}">
      <div class="tutor-tool-head">${head}</div>
      ${evt.code ? `<pre class="tutor-code">${esc(evt.code)}</pre>` : ''}
      ${mediaTagHtml(evt.media_url, evt.media_kind)}
      ${out ? `<pre class="tutor-code tutor-tool-output">${esc(out)}</pre>` : ''}
    </div>`;
  }

  // History replay only has the flattened `content` string persisted for a
  // role="tool" message (no separate stdout/stderr, no media_url field) -
  // render_plot's content embeds the media URL as plain text (see
  // _handle_render_plot in tutor_engine.py), so pull it back out here.
  const MEDIA_URL_RE = /\/learn\/tutor\/media\/\S+/;

  function toolHistoryBubble(m) {
    const mediaMatch = MEDIA_URL_RE.exec(m.content || '');
    return `<div class="tutor-bubble tutor-tool-bubble" data-msg-id="${esc(m.id || '')}">
      <div class="tutor-tool-head">🔧 <code>${esc(m.tool_name || 'tool')}</code></div>
      ${mediaMatch ? mediaTagHtml(mediaMatch[0]) : ''}
      <pre class="tutor-code tutor-tool-output">${esc(m.content)}</pre>
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

  // Drives one streamed turn's live rendering into threadEl - shared by
  // send() (POST .../messages) and regenerate() (POST .../regenerate),
  // which differ only in which request kicks the stream off and what (if
  // anything) they put in the thread before calling this.
  async function streamIntoThread(threadEl, fetchPromise) {
    // A turn can span multiple assistant text spans with tool calls
    // interleaved between them (see tutor_engine.py's round loop) - each
    // gets its own bubble so the DOM stays in chronological order instead
    // of text-before and text-after a tool call fighting over one bubble.
    let contentEl = null;
    let raw = '';
    let pendingToolId = null;
    const newAssistantBubble = () => {
      // drop the previous bubble if the model went straight to a tool
      // call and never put any text in it - otherwise every tool call
      // leaves a stray empty bubble behind it in the thread
      if (contentEl && !contentEl.innerHTML.trim()) contentEl.closest('.tutor-bubble')?.remove();
      const liveId = 'live-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7);
      threadEl.insertAdjacentHTML('beforeend', `<div class="tutor-bubble tutor-bubble-assistant" data-msg-id="${liveId}"><div class="tutor-bubble-content"></div></div>`);
      contentEl = threadEl.querySelector(`[data-msg-id="${liveId}"] .tutor-bubble-content`);
      raw = '';
    };
    newAssistantBubble();
    threadEl.scrollTop = threadEl.scrollHeight;

    try {
      const resp = await fetchPromise;
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
          } else if (event.type === 'tool_call') {
            pendingToolId = 'tool-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7);
            threadEl.insertAdjacentHTML('beforeend', toolCallPendingBubble(pendingToolId, event.name, event.args));
            threadEl.scrollTop = threadEl.scrollHeight;
          } else if (event.type === 'tool_result') {
            const pendingEl = pendingToolId && threadEl.querySelector(`[data-tool-id="${pendingToolId}"]`);
            if (pendingEl) {
              pendingEl.outerHTML = toolResultBubbleHtml(pendingToolId, event);
              const resultEl = threadEl.querySelector(`[data-tool-id="${pendingToolId}"]`);
              if (resultEl) hydrateMedia(resultEl);
            }
            pendingToolId = null;
            threadEl.scrollTop = threadEl.scrollHeight;
            newAssistantBubble(); // whatever text comes next belongs after this result
          } else if (event.type === 'error') {
            contentEl.innerHTML += `<p class="tutor-error">could not reply: ${esc(event.content)}</p>`;
          }
        }
      }
    } catch (err) {
      contentEl.innerHTML += `<p class="tutor-error">${esc(err.message || err)}</p>`;
    } finally {
      // drop a trailing bubble that never got any text (e.g. the turn
      // ended right after a tool result with nothing further to say)
      if (contentEl && !contentEl.innerHTML.trim()) contentEl.closest('.tutor-bubble')?.remove();
    }
  }

  async function renderChat(el, track, Api, onExit) {
    el.innerHTML = `<div class="tutor-shell fade-in">
      <header class="tutor-topbar">
        <button data-tutor-exit class="forge-lesson-exit" aria-label="Exit tutor">×</button>
        <div class="tutor-topbar-title"><span>Tutor</span><h2>${esc(track.title)}</h2></div>
        <button data-tutor-regenerate class="ghost xs" disabled>regenerate last reply</button>
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
    const regenerateBtn = el.querySelector('[data-tutor-regenerate]');

    function updateRegenerateAvailability() {
      regenerateBtn.disabled = sendBtn.disabled || !threadEl.querySelector('.tutor-bubble-user');
    }
    function setBusy(busy) {
      sendBtn.disabled = busy;
      updateRegenerateAvailability();
    }

    async function loadHistory() {
      const messages = await Api.get(`/learn/tracks/${track.id}/tutor/messages`);
      const visible = messages.filter((m) => m.role === 'user' || m.role === 'assistant' || m.role === 'tool');
      const html = visible.map((m) => {
        if (m.role === 'tool') return toolHistoryBubble(m);
        // an assistant message that only requested a tool call (no visible
        // text) has nothing to show on its own - the tool bubble covers it
        if (m.role === 'assistant' && m.tool_calls_json && !String(m.content || '').trim()) return '';
        return bubble(m);
      }).join('');
      threadEl.innerHTML = html || '<p class="muted small">Say hello to start.</p>';
      threadEl.scrollTop = threadEl.scrollHeight;
      hydrateMedia(threadEl);
      updateRegenerateAvailability();
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
      setBusy(true);
      if (threadEl.querySelector('.muted.small')) threadEl.innerHTML = '';
      threadEl.insertAdjacentHTML('beforeend', bubble({ role: 'user', content: text }));

      await streamIntoThread(threadEl, fetch(`/learn/tracks/${track.id}/tutor/messages`, {
        method: 'POST',
        headers: { 'X-API-Key': localStorage.getItem('hive-key') || '', 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: text }),
      }));

      setBusy(false);
      input.focus();
    }

    async function regenerate() {
      const userBubbles = threadEl.querySelectorAll('.tutor-bubble-user');
      if (regenerateBtn.disabled || !userBubbles.length) return;
      setBusy(true);
      // remove the old reply (and any tool bubbles it produced) - the
      // server does the same trim to its own history, see
      // tutor_store.truncate_after_last_user_message.
      let node = userBubbles[userBubbles.length - 1].nextElementSibling;
      while (node) {
        const next = node.nextElementSibling;
        node.remove();
        node = next;
      }

      await streamIntoThread(threadEl, fetch(`/learn/tracks/${track.id}/tutor/regenerate`, {
        method: 'POST',
        headers: { 'X-API-Key': localStorage.getItem('hive-key') || '' },
      }));

      setBusy(false);
    }

    sendBtn.onclick = send;
    regenerateBtn.onclick = regenerate;
    input.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };

    await loadHistory();
    input.focus();
  }

  return { studyPanelSection, wireStudyPanelSection, renderChat, openSetupModal };
})();
