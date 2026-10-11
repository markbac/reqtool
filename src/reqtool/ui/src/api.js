/**
 * api.js -- Thin fetch wrapper over the reqtool backend.
 * Base URL resolves to same host in production; env var for dev.
 */

function getBaseUrl() {
  const customServer = localStorage.getItem('reqtool:server_url');
  if (customServer && customServer.trim()) {
    return customServer.trim().replace(/\/+$/, '');
  }
  return import.meta.env.VITE_API_BASE ?? '';
}

// Same-origin sessions live in HttpOnly cookies (SEC-19). Only a custom server URL (cross-origin) falls back to a stored bearer token.
const isCrossOrigin = () => Boolean((localStorage.getItem('reqtool:server_url') || '').trim());
const bearerToken = () => (isCrossOrigin() ? localStorage.getItem('reqtool:auth_token') : null);

let refreshing = null;

/** Ask the server for a new access cookie. Concurrent callers share one request. */
function refreshSession() {
  if (!refreshing) {
    refreshing = fetch(`${getBaseUrl()}/auth/refresh`, { method: 'POST', headers: { 'X-Reqtool-CSRF': '1' } })
      .then(r => r.ok, () => false)
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

async function send(method, path, body) {
  const headers = { 'Content-Type': 'application/json', 'X-Reqtool-CSRF': '1' };
  const token = bearerToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const opts = { method, headers };
  if (body !== null) opts.body = JSON.stringify(body);
  return fetch(`${getBaseUrl()}${path}`, opts);
}

async function request(method, path, body = null) {
  let res = await send(method, path, body);
  const authPath = path === '/auth/login' || path === '/auth/refresh' || path === '/auth/logout';
  if (res.status === 401 && !authPath && !bearerToken() && await refreshSession()) {
    res = await send(method, path, body);
  }
  if (res.status === 401 && path !== '/auth/login') {
    // Server requires authentication (or the session expired): ask the app to show the login dialog.
    try { window.dispatchEvent(new CustomEvent('reqtool:unauthorized')); } catch { /* non-browser */ }
  }
  if (!res.ok) {
    let detail;
    try { detail = await res.json(); } catch { detail = { message: res.statusText }; }
    const msg = detail?.detail?.message ?? detail?.message ?? detail?.detail ?? res.statusText;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status; err.detail = detail?.detail;
    throw err;
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
    history:       (uid)           => get(`/requirements/${uid}/history`),
    transition:    (uid, status, extra = {}) => post(`/requirements/${uid}/transition`, { to_state: status, ...extra }),
    transitions:   (uid)           => get(`/requirements/${uid}/transitions`),
    raise:         (uid, reqType)  => post(`/requirements/${uid}/raise`, reqType ? { req_type: reqType } : {}),
    lint:          (uid)           => get(`/requirements/${uid}/lint`),
    relationships: (uid)         => get(`/requirements/${uid}/relationships`),
    addAc:         (uid, body)   => post(`/requirements/${uid}/ac`, body),
    updateAc:      (uid, acUid, body) => put(`/requirements/${uid}/ac/${acUid}`, body),
    deleteAc:      (uid, acUid)  => del(`/requirements/${uid}/ac/${acUid}`),
    clone:         (uid, newId = '') => post(`/requirements/${uid}/clone${newId ? '?new_id=' + encodeURIComponent(newId) : ''}`),
    bulk:          (body)        => post('/requirements/bulk', body),
    clearSuspect:  (uid, idx)    => post(`/requirements/${uid}/relationships/${idx}/clear-suspect`),
    trace:         (uid)         => get(`/requirements/${uid}/trace`),
    summary:       (uid)         => get(`/requirements/${uid}/summary`),
    lifecycle:     (uid)         => get(`/requirements/${uid}/lifecycle`),
    quality:       (uid)         => get(`/requirements/${uid}/quality`),
    impact:        (uid)         => get(`/requirements/${uid}/impact`),
    impactPreview: (uid, body)   => post(`/requirements/${uid}/impact-preview`, body),
    progress:      (uid)         => get(`/requirements/${uid}/progress`),
    rollup:        (uid)         => get(`/requirements/${uid}/rollup`),
    reviewRequests:(uid)         => get(`/requirements/${uid}/review-requests`),
    requestReview: (uid, reviewers) => post(`/requirements/${uid}/review-requests`, { reviewers }),
    approvals:     (uid)         => get(`/requirements/${uid}/approvals`),
  },
  principles: {
    list:   (params = {}) => get('/principles?' + new URLSearchParams(params)),
    areas:  ()          => get('/principles/areas'),
    packs:  ()          => get('/principles/packs'),
    addPack: (area)     => post(`/principles/packs/${encodeURIComponent(area)}`, {}),
    vocabulary:    ()   => get('/principles/vocabulary'),
    setVocabulary: (body) => put('/principles/vocabulary', body),
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
    resolve: (uid, body)   => post(`/tbds/${uid}/resolve`, { resolved_by: localStorage.getItem('reqtool:username') || 'user', ...body }),
  },
  decisions: {
    list:    (params = {}) => get('/decisions?' + new URLSearchParams(params)),
    get:     (uid)         => get(`/decisions/${uid}`),
    create:  (body)        => post('/decisions', body),
    update:  (uid, body)   => put(`/decisions/${uid}`, body),
    delete:  (uid)         => del(`/decisions/${uid}`),
    commit:  (uid, body)   => post(`/decisions/${uid}/commit`, body),
    resolve: (uid, body)   => post(`/decisions/${uid}/resolve`, body),
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
  repo: {
    get:    () => get('/repo'),
    switch: (path) => post('/repo/switch', { path }),
    init:   (body) => post('/repo/init', body),
  },
  auth: {
    login:     (username, password) => post('/auth/login', { username, password }),
    me:        ()                   => get('/auth/me'),
    listUsers: ()                   => get('/auth/users'),
    createUser:(body)               => post('/auth/users', body),
    logout:    ()                   => post('/auth/logout'),
  },
  attachments: {
    list:     (uid)                         => get(`/artefacts/${uid}/attachments`),
    upload:   (uid, filename, data, description = '') =>
      fetch(`${getBaseUrl()}/artefacts/${uid}/attachments`, {
        method: 'POST',
        headers: {
          'Content-Disposition': `attachment; filename="${filename}"`,
          'X-Description': description,
        },
        body: data,
      }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e?.detail?.message || 'Upload failed')))),
    download: (uid, filename) => `${getBaseUrl()}/artefacts/${uid}/attachments/${encodeURIComponent(filename)}`,
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
  help: {
    get: (topic) => get(topic ? `/help?topic=${topic}` : '/help'),
  },
  kanban: {
    get: (params = {}) => get('/kanban?' + new URLSearchParams(params)),
  },
  modules: {
    list:    ()                   => get('/modules'),
    get:     (id)                 => get(`/modules/${id}`),
    verify:  (id)                 => get(`/modules/${id}/verify`),
    include: (productId, moduleId) => post(`/products/${productId}/modules`, { module_id: moduleId }),
    create:  (body)               => post('/modules', body),
    version: (id, body)           => post(`/modules/${id}/version`, body),
    clone:   (id, newId)          => post(`/modules/${id}/clone`, { id: newId }),
    consumers: (id)               => get(`/modules/${id}/consumers`),
    pin:     (id, ref)            => post(`/modules/${id}/pin`, { ref }),
    updatePreview: (id, ref)      => get(`/modules/${id}/update-preview?ref=${encodeURIComponent(ref)}`),
    fetchRemote: (id)             => post(`/modules/${id}/fetch-remote`),
    importInto: (id, productId)   => post(`/modules/${id}/import?product_id=${encodeURIComponent(productId)}`),
    verifyFor: (id, productId)    => get(`/modules/${id}/verify?product_id=${encodeURIComponent(productId)}`),
  },
  hierarchy: {
    get:     ()         => get('/hierarchy'),
    types:   ()         => get('/hierarchy/types'),
    children:(reqType)  => get(`/hierarchy/children/${reqType}`),
  },
  diff: (since = 'HEAD~1') => get(`/diff?since=${encodeURIComponent(since)}`),
  render: {
    markdown: (text) => post('/render/markdown', { text }),
    plantuml: (text) => post('/render/plantuml', { text }),
  },
  health: () => get('/health'),
  workflow: {
    get:    ()     => get('/workflow'),
    update: (body) => put('/workflow', body),
    mermaid: ()    => get('/workflow/mermaid'),
  },
  permissions: () => get('/permissions'),
  rules: {
    get:       ()          => get('/rules'),
    save:      (body)      => put('/rules', body),
    preview:   (uid, to)   => post('/rules/preview', { uid, to_state: to }),
    overrides: ()          => get('/rules/overrides'),
  },
  workflows: {
    list:    ()               => get('/workflows'),
    preview: (definition, id) => post('/workflows/preview', { definition, id }),
    create:  (body)           => post('/workflows', body),
    save:    (id, definition) => put(`/workflows/${encodeURIComponent(id)}`, definition),
    remove:  (id)             => del(`/workflows/${encodeURIComponent(id)}`),
    assign:  (typeId, workflow) => put(`/hierarchy/types/${encodeURIComponent(typeId)}/workflow`, { workflow }),
  },
  lint: {
    config:     ()     => get('/lint/config'),
    saveConfig: (body) => put('/lint/config', body),
    all:        (severity = 'info') => get('/lint?severity=' + severity),
  },
  templates: {
    list:   ()     => get('/templates'),
    save:   (body) => put('/templates', body),
  },
  baselines: {
    list:   ()     => get('/baselines'),
    create: (body) => post('/baselines', body),
    diff:   (name) => get(`/baselines/${encodeURIComponent(name)}/diff`),
    fieldDiff: (a, b = 'HEAD') => get(`/baselines/field-diff?baseline_a=${encodeURIComponent(a)}&baseline_b=${encodeURIComponent(b)}`),
  },
  overview:  (product) => get('/overview' + (product ? `?product=${encodeURIComponent(product)}` : '')),
  roadmap:   ()        => get('/roadmap'),
  gate:      (product) => get('/gate' + (product ? `?product=${encodeURIComponent(product)}` : '')),
  doctor:    ()        => get('/doctor'),
  trend:     ()        => get('/trend'),
  query:     (q)       => get(`/query?q=${encodeURIComponent(q)}`),
  qualityCheck: (body) => post('/quality/check', body),
  suggestDuplicates: (body) => post('/duplicates/suggest', body),
  reviews:   (reviewer) => get(`/reviews?reviewer=${encodeURIComponent(reviewer)}`),
  notifications: {
    list:  (user, unread = false) => get(`/notifications?user=${encodeURIComponent(user)}${unread ? '&unread=true' : ''}`),
    read:  (id, user)  => post(`/notifications/${id}/read?user=${encodeURIComponent(user)}`),
    prefs: (user)      => get(`/notifications/preferences/${encodeURIComponent(user)}`),
    setPrefs: (user, body) => put(`/notifications/preferences/${encodeURIComponent(user)}`, body),
  },
  changesets: {
    list:   ()           => get('/changesets'),
    create: (name)       => post('/changesets', { name }),
    diff:   (name)       => get(`/changesets/${encodeURIComponent(name)}/diff`),
    merge:  (name, reviewedBy) => post(`/changesets/${encodeURIComponent(name)}/merge`, { reviewed_by: reviewedBy }),
    switchTo: (branch)   => post('/changesets/switch', { branch }),
  },
  filterPresets: {
    list:   ()     => get('/filter-presets'),
    save:   (id, body) => put(`/filter-presets/${encodeURIComponent(id)}`, body),
    delete: (id)   => del(`/filter-presets/${encodeURIComponent(id)}`),
  },
  snapshotUrl: (baseline = '') => `${getBaseUrl()}/snapshot.zip${baseline ? '?baseline=' + encodeURIComponent(baseline) : ''}`,
  testResults: (xml, source = 'ui') => fetch(`${getBaseUrl()}/test-results?source=${encodeURIComponent(source)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/xml', 'X-Reqtool-CSRF': '1' }, body: xml,
  }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e?.detail?.message || 'Upload failed')))),
  metrics: {
    get: () => get('/metrics'),
  },
  iterations: {
    list:   ()     => get('/iterations'),
    get:    (id)   => get(`/iterations/${encodeURIComponent(id)}`),
    create: (body) => post('/iterations', body),
    delete: (id)   => del(`/iterations/${encodeURIComponent(id)}`),
    metrics:(id)   => get(`/iterations/${encodeURIComponent(id)}/metrics`),
  },
  analysis: {
    detectDuplicates: (threshold = 0.7) => get('/analysis/detect-duplicates?threshold=' + threshold),
    generateAc:        (title, description = '') => post('/analysis/generate-ac', { title, description }),
    generateTests:     (uid) => post(`/analysis/generate-tests/${uid}`, {}),
  },
  traceability: {
    gaps: () => get('/traceability/gaps'),
    coverage: (source, target) => get(`/traceability/matrix?source_type=${encodeURIComponent(source)}&target_type=${encodeURIComponent(target)}`),
  },
  automation: {
    schema:      ()     => get('/automation/schema'),
    getRules:    ()     => get('/automation/rules'),
    updateRules: (body) => put('/automation/rules', body),
  },
  importCsv: async (csvText) => {
    const res = await fetch(`${getBaseUrl()}/import/csv/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv' },
      body: csvText,
    });
    if (!res.ok) {
      let detail; try { detail = await res.json(); } catch { detail = { message: res.statusText }; }
      const rows = (detail?.detail?.errors ?? []).slice(0, 5).map(e => `row ${e.row}${e.id ? ` (${e.id})` : ''}: ${e.error}`);
      const more = (detail?.detail?.errors?.length ?? 0) > 5 ? `; and ${detail.detail.errors.length - 5} more` : '';
      const base = detail?.detail?.message ?? detail?.message ?? res.statusText;
      const err = new Error(rows.length ? `${base}. ${rows.join('; ')}${more}` : base);
      err.detail = detail?.detail;
      throw err;
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
    jsx:          (body) => post('/export/jsx', body),
    markdown:     (body) => post('/export/markdown', body),
    csv:          (body) => post('/export/csv', body),
    reqif:        () => get('/export/reqif'),
    pdf:          (body) => post('/export/pdf', body),
    adrUrl: () => `${getBaseUrl()}/export/adr`,
    auditPackage: (params = {}) => {
      // Same-origin navigations carry the session cookie. A cross-origin server needs the token as a query parameter.
      const token = bearerToken();
      return `${getBaseUrl()}/export/audit-package?${new URLSearchParams(token ? { ...params, access_token: token } : params)}`;
    },
  },
};
