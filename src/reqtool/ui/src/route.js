/**
 * route.js -- Page addresses (#372). Every area, tab and selected item is in the address, so Back, bookmarks
 * and reload work:
 *
 *   #/requirements/tree?item=<uid>&type=requirement&tab=links&product=sensor_pro
 *   #/work/board?product=sensor_pro
 *   #/decisions?item=<uid>
 *   #/settings/workflows
 *
 * The hash form needs nothing from the server, so it works from any path and in the desktop build.
 * Old links (`/?uid=...&type=...`) are read once and turned into the new form.
 */

export const AREAS = {
  requirements: { label: 'Requirements', tabs: ['tree', 'table', 'modules', 'baselines', 'changesets', 'writing', 'duplicates'] },
  work:         { label: 'Work',         tabs: ['issues', 'backlog', 'tree', 'board', 'roadmap', 'iterations'] },
  decisions:    { label: 'Decisions',    tabs: [] },
  principles:   { label: 'Principles',   tabs: ['library', 'cited'] },
  insights:     { label: 'Insights',     tabs: ['overview', 'coverage', 'traceability', 'views', 'diagrams'] },
  settings:     { label: 'Settings',     tabs: ['workflows', 'fields', 'vocabularies', 'templates', 'automation', 'webhooks', 'writing', 'repository'] },
};

export const DEFAULT_TAB = {
  requirements: 'tree', work: 'board', decisions: '', principles: 'library', insights: 'overview', settings: 'workflows',
};

/** Parse a location hash (and, for old links, the query string) into a route. */
export function parseRoute(hash = '', search = '') {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?');
  const parts = path.split('/').filter(Boolean);
  const params = new URLSearchParams(query);
  let area = AREAS[parts[0]] ? parts[0] : 'requirements';
  let tab = parts[1] && AREAS[area].tabs.includes(parts[1]) ? parts[1] : DEFAULT_TAB[area];
  let item = params.get('item') || null;
  let type = params.get('type') || null;
  if (!parts.length && search) {            // an old link: /?uid=...&type=...
    const old = new URLSearchParams(search);
    item = old.get('uid') || item;
    type = old.get('type') || type;
    if (type === 'tbd' || type === 'decision') { area = 'decisions'; tab = ''; }
    if (type === 'principle') { area = 'principles'; tab = 'library'; }
  }
  if (type === 'tbd') type = 'decision';
  return {
    area, tab, item, type: item ? (type || defaultType(area)) : null,
    editorTab: params.get('tab') || null, product: params.get('product') || null,
  };
}

/** The hash for a route. Empty parts are left out. */
export function buildRoute({ area = 'requirements', tab, item, type, editorTab, product }) {
  const path = [area, tab && tab !== DEFAULT_TAB[area] ? tab : null].filter(Boolean).join('/');
  const params = new URLSearchParams();
  if (item) params.set('item', item);
  if (item && type && type !== defaultType(area)) params.set('type', type);
  if (item && editorTab) params.set('tab', editorTab);
  if (product) params.set('product', product);
  const q = params.toString();
  return `#/${path}${q ? `?${q}` : ''}`;
}

function defaultType(area) {
  return area === 'decisions' ? 'decision' : area === 'principles' ? 'principle' : 'requirement';
}

const PRODUCT_KEY = 'reqtool:product';

/** The product last used in this browser for this repository (wrapped: storage can be unavailable). */
export function rememberedProduct(repoId) {
  try { return localStorage.getItem(`${PRODUCT_KEY}:${repoId || ''}`); } catch { return null; }
}

export function rememberProduct(repoId, productId) {
  try {
    if (productId) localStorage.setItem(`${PRODUCT_KEY}:${repoId || ''}`, productId);
    else localStorage.removeItem(`${PRODUCT_KEY}:${repoId || ''}`);
  } catch { /* storage unavailable: the address still carries the product */ }
}
