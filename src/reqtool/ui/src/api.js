/**
 * api.js -- Thin fetch wrapper over the reqtool backend.
 * Base URL resolves to same host in production; env var for dev.
 */

const BASE = import.meta.env.VITE_API_BASE ?? '';

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    let detail;
    try { detail = await res.json(); } catch { detail = { message: res.statusText }; }
    const msg = detail?.detail?.message ?? detail?.message ?? res.statusText;
    throw new Error(msg);
  }
  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) return res.json();
  return res.blob();
}

const get  = (path)        => request('GET',    path);
const post = (path, body)  => request('POST',   path, body ?? {});
const put  = (path, body)  => request('PUT',    path, body);
const del  = (path)        => request('DELETE', path);

export const api = {
  requirements: {
    list:          (params = {}) => get('/requirements?' + new URLSearchParams(params)),
    tree:          (product, variant) => get('/requirements/tree?product=' + product + (variant ? '&variant=' + variant : '')),
    get:           (uid)         => get(`/requirements/${uid}`),
    create:        (body)        => post('/requirements', body),
    update:        (uid, body)   => put(`/requirements/${uid}`, body),
    delete:        (uid)         => del(`/requirements/${uid}`),
    commit:        (uid, body)   => post(`/requirements/${uid}/commit`, body),
    approve:       (uid, body)   => post(`/requirements/${uid}/approve`, body),
    history:       (uid)         => get(`/requirements/${uid}/history`),
    relationships: (uid)         => get(`/requirements/${uid}/relationships`),
    addAc:         (uid, body)   => post(`/requirements/${uid}/ac`, body),
    updateAc:      (uid, acUid, body) => put(`/requirements/${uid}/ac/${acUid}`, body),
    deleteAc:      (uid, acUid)  => del(`/requirements/${uid}/ac/${acUid}`),
    clone:         (uid, newId = '') => post(`/requirements/${uid}/clone${newId ? '?new_id=' + encodeURIComponent(newId) : ''}`),
    bulk:          (body)        => post('/requirements/bulk', body),
  },
  principles: {
    list:   ()          => get('/principles'),
    get:    (uid)       => get(`/principles/${uid}`),
    create: (body)      => post('/principles', body),
    update: (uid, body) => put(`/principles/${uid}`, body),
    delete: (uid)       => del(`/principles/${uid}`),
    commit: (uid, body) => post(`/principles/${uid}/commit`, body),
  },
  tbds: {
    list:    (params = {}) => get('/tbds?' + new URLSearchParams(params)),
    get:     (uid)         => get(`/tbds/${uid}`),
    create:  (body)        => post('/tbds', body),
    update:  (uid, body)   => put(`/tbds/${uid}`, body),
    delete:  (uid)         => del(`/tbds/${uid}`),
    commit:  (uid, body)   => post(`/tbds/${uid}/commit`, body),
    resolve: (uid, body)   => post(`/tbds/${uid}/resolve`, body),
  },
  products: {
    list:   ()      => get('/products'),
    get:    (id)    => get(`/products/${id}`),
    create: (body)  => post('/products', body),
    tree:   (id, variant) => get(`/products/${id}/tree` + (variant ? '?variant=' + variant : '')),
    matrix: (id)    => get(`/products/${id}/matrix`),
  },
  enums: {
    all:       () => get('/enums'),
    core:      () => get('/enums/core'),
    repo:      () => get('/enums/repo'),
    updateRepo: (body) => put('/enums/repo', body),
  },
  config: { get: () => get('/config') },
  attachments: {
    list:     (uid)                         => get(`/artefacts/${uid}/attachments`),
    upload:   (uid, filename, data, description = '') =>
      fetch(`${BASE}/artefacts/${uid}/attachments`, {
        method: 'POST',
        headers: {
          'Content-Disposition': `attachment; filename="${filename}"`,
          'X-Description': description,
        },
        body: data,
      }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e?.detail?.message || 'Upload failed')))),
    download: (uid, filename) => `${BASE}/artefacts/${uid}/attachments/${encodeURIComponent(filename)}`,
    delete:   (uid, filename) => del(`/artefacts/${uid}/attachments/${encodeURIComponent(filename)}`),
  },
  comments: {
    list:    (uid)                       => get(`/artefacts/${uid}/comments`),
    add:     (uid, body)                 => post(`/artefacts/${uid}/comments`, body),
    update:  (uid, commentUid, body)     => put(`/artefacts/${uid}/comments/${commentUid}`, body),
    resolve: (uid, commentUid, resolved) => post(`/artefacts/${uid}/comments/${commentUid}/resolve`, { resolved }),
    delete:  (uid, commentUid)           => del(`/artefacts/${uid}/comments/${commentUid}`),
  },
  customFields: {
    schema: ()     => get('/custom-fields'),
    save:   (body) => put('/custom-fields', body),
  },
  webhooks: {
    list:   ()     => get('/webhooks'),
    add:    (body) => post('/webhooks', body),
    delete: (idx)  => del(`/webhooks/${idx}`),
  },
  kanban: {
    get: (params = {}) => get('/kanban?' + new URLSearchParams(params)),
  },
  modules: {
    list:   ()     => get('/modules'),
    get:    (id)   => get(`/modules/${id}`),
    verify: (id)   => get(`/modules/${id}/verify`),
  },
  hierarchy: {
    get:     ()         => get('/hierarchy'),
    types:   ()         => get('/hierarchy/types'),
    children:(reqType)  => get(`/hierarchy/children/${reqType}`),
  },
  diff: (since = 'HEAD~1') => get(`/diff?since=${encodeURIComponent(since)}`),
  render: { markdown: (text) => post('/render/markdown', { text }) },
  health: () => get('/health'),
  workflow: {
    get:    ()     => get('/workflow'),
    update: (body) => put('/workflow', body),
  },
  templates: {
    list:   ()     => get('/templates'),
    save:   (body) => put('/templates', body),
  },
  baselines: {
    list:   ()     => get('/baselines'),
    create: (body) => post('/baselines', body),
    diff:   (name) => get(`/baselines/${encodeURIComponent(name)}/diff`),
  },
  metrics: {
    get: () => get('/metrics'),
  },
  importCsv: async (csvText) => {
    const res = await fetch(`${BASE}/import/csv/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv' },
      body: csvText,
    });
    if (!res.ok) {
      let detail; try { detail = await res.json(); } catch { detail = { message: res.statusText }; }
      throw new Error(detail?.detail?.message ?? detail?.message ?? res.statusText);
    }
    return res.json();
  },
  search: (q, limit = 20) => get(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  validate: {
    all:    ()    => get('/validate'),
    single: (uid) => get(`/validate/${uid}`),
  },
  git: {
    status: ()     => get('/git/status'),
    commit: (body) => post('/git/commit', body),
    log:    (uid)  => get(`/git/log/${uid}`),
  },
  exports: {
    jsx:      (body) => post('/export/jsx', body),
    markdown: (body) => post('/export/markdown', body),
    csv:      (body) => post('/export/csv', body),
  },
};
