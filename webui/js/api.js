/* api.js — fetch wrapper + key handling */
const Api = (() => {
  let KEY = localStorage.getItem('hive-key') || '';

  async function req(path, opts = {}) {
    const r = await fetch(path, {
      ...opts,
      headers: {
        'X-API-Key': KEY,
        'Content-Type': 'application/json',
        ...(opts.headers || {}),
      },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (r.status === 401) { setKey(''); location.reload(); throw new Error('unauthorized'); }
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try { msg = (await r.json()).detail || msg; } catch (e) { /* keep */ }
      throw new Error(msg);
    }
    return r.status === 204 ? null : r.json();
  }

  function setKey(k) { KEY = k; k ? localStorage.setItem('hive-key', k)
                                 : localStorage.removeItem('hive-key'); }

  // ---- timezone display helpers ----
  // The API returns UTC instants (…+00:00 / Z). Render them in a named zone.
  function fmtInZone(iso, tz, opts) {
    if (!iso) return '';
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return new Intl.DateTimeFormat('en-US', { timeZone: tz, ...opts }).format(d);
  }
  function dayInZone(iso, tz) {
    // YYYY-MM-DD as seen in tz
    const parts = fmtInZone(iso, tz, { year: 'numeric', month: '2-digit', day: '2-digit' });
    const [m, d, y] = parts.split('/');
    return `${y}-${m}-${d}`;
  }

  return {
    setKey, hasKey: () => !!KEY, fmtInZone, dayInZone,
    get:  (p)    => req(p),
    post: (p, b) => req(p, { method: 'POST',  body: b }),
    put:  (p, b) => req(p, { method: 'PUT',   body: b }),
    patch:(p, b) => req(p, { method: 'PATCH', body: b }),
    del:  (p)    => req(p, { method: 'DELETE' }),
  };
})();
