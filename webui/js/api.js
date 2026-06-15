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

  return {
    setKey, hasKey: () => !!KEY,
    get:  (p)    => req(p),
    post: (p, b) => req(p, { method: 'POST',  body: b }),
    put:  (p, b) => req(p, { method: 'PUT',   body: b }),
    patch:(p, b) => req(p, { method: 'PATCH', body: b }),
    del:  (p)    => req(p, { method: 'DELETE' }),
  };
})();
