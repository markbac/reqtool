// Creating items from the landing page, the Templates panel and Help: one path, so the item is
// always created, selected and shown in the tree.
import { api } from './api';

export function templateBody(tmpl, parentId = null) {
  const { content, ...rest } = tmpl.fields || {};
  return {
    title: `New ${tmpl.label}`,
    parentId,
    ...rest,
    content: content || { description: 'The system shall...', rationale: '', extended_description: '' },
  };
}

export function typeBody(reqType, label, parentId = null) {
  return { title: `New ${label || reqType}`, parentId, req_type: reqType };
}

// Create, select and refresh the tree. Returns the new item, or null after a toast on failure.
export async function createAndOpen(body, { dispatch, toast, hasProduct = true }) {
  if (!hasProduct) { toast('Select a product first', 'info'); return null; }
  try {
    const item = await api.requirements.create(body);
    dispatch({ type: 'SELECT', uid: item.uid, artefactType: 'requirement' });
    window.dispatchEvent(new Event('reqtool:tree-changed'));
    return item;
  } catch (err) {
    toast(err.message, 'error');
    return null;
  }
}

// Types to offer for quick create: the repository's own, top-level types first.
export function quickTypes(hierarchy) {
  const types = hierarchy?.types || {};
  const rules = hierarchy?.hierarchy || {};
  const children = new Set(Object.values(rules).flatMap(r => r.allowed_children || []));
  return Object.entries(types)
    .map(([id, t]) => ({ id, label: t.label || id, icon: t.icon || '', desc: t.description || '', top: !children.has(id) }))
    .sort((a, b) => (b.top - a.top) || a.label.localeCompare(b.label));
}
