// Re-parenting from the tree (#320): which items an item may be moved under.
// The rules come from the server (GET /hierarchy), so the picker and drag and drop offer what it will accept.

// Every item below ``node`` (not including it).
export function descendantUids(node) {
  const out = new Set();
  const walk = (n) => (n.children || []).forEach(c => { out.add(c.uid); walk(c); });
  if (node) walk(node);
  return out;
}

// Flatten the tree to the items that can take a child. Module groups and module items are read-only.
export function candidateParents(tree) {
  const out = [];
  const walk = (nodes, depth) => (nodes || []).forEach(n => {
    if (!n._is_module_group && !n.module) out.push({ node: n, depth });
    walk(n.children, depth + 1);
  });
  walk(tree, 0);
  return out;
}

// Can ``node`` be moved under ``target``? ``rules`` is the ``hierarchy`` map from GET /hierarchy.
// Returns { ok, reason }; the reason is shown to the user when ok is false.
export function canMoveUnder(node, target, rules, currentParentUid = null) {
  if (!node || !target) return { ok: false, reason: 'Nothing to move' };
  if (target.uid === node.uid) return { ok: false, reason: 'An item cannot be moved under itself' };
  if (descendantUids(node).has(target.uid)) return { ok: false, reason: 'An item cannot be moved under one of its own descendants' };
  if (target.uid === currentParentUid) return { ok: false, reason: `${node.id} is already under ${target.id}` };
  const allowed = rules?.[target.req_type]?.allowed_children;
  if (!allowed || !allowed.includes(node.req_type)) {
    return { ok: false, reason: `A ${node.req_type} cannot go under a ${target.req_type}` };
  }
  return { ok: true, reason: '' };
}

// The node that lists ``uid`` as a child, or null for a top-level item.
export function parentOf(tree, uid) {
  for (const n of tree || []) {
    if ((n.children || []).some(c => c.uid === uid)) return n;
    const hit = parentOf(n.children, uid);
    if (hit) return hit;
  }
  return null;
}
