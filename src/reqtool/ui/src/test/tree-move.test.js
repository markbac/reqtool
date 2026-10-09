import { describe, it, expect } from 'vitest';
import { descendantUids, candidateParents, canMoveUnder, parentOf } from '../treeMove';

const n = (uid, req_type, children = [], extra = {}) => ({ uid, id: uid.toUpperCase(), req_type, children, ...extra });
const tree = [
  n('th', 'theme', [
    n('in', 'initiative', [
      n('ep', 'epic', [n('st', 'story', [n('tk', 'task')])]),
      n('ep2', 'epic'),
    ]),
  ]),
  n('grp', 'functional', [n('modreq', 'functional', [], { module: 'm1' })], { _is_module_group: true }),
];
const rules = {
  theme: { allowed_children: ['initiative'] },
  initiative: { allowed_children: ['epic'] },
  epic: { allowed_children: ['feature', 'story', 'task'] },
  story: { allowed_children: ['task'] },
  task: { allowed_children: [] },
};
const find = (uid) => {
  const walk = (ns) => ns.reduce((hit, x) => hit || (x.uid === uid ? x : walk(x.children)), null);
  return walk(tree);
};

describe('tree move rules (#320)', () => {
  it('lists every item below a node, but not the node', () => {
    expect([...descendantUids(find('in'))].sort()).toEqual(['ep', 'ep2', 'st', 'tk']);
    expect(descendantUids(null).size).toBe(0);
  });

  it('finds the parent of a node, or null at the top level', () => {
    expect(parentOf(tree, 'st').uid).toBe('ep');
    expect(parentOf(tree, 'th')).toBeNull();
  });

  it('offers read-only module items as no target', () => {
    const uids = candidateParents(tree).map(c => c.node.uid);
    expect(uids).toContain('tk');
    expect(uids).not.toContain('grp');
    expect(uids).not.toContain('modreq');
  });

  it('allows a move the hierarchy permits', () => {
    expect(canMoveUnder(find('st'), find('ep2'), rules, 'ep').ok).toBe(true);
  });

  it('refuses a type the target does not allow, and says why', () => {
    const v = canMoveUnder(find('ep'), find('th'), rules, 'in');
    expect(v.ok).toBe(false);
    expect(v.reason).toMatch(/epic cannot go under a theme/);
  });

  it('refuses a move onto itself or a descendant', () => {
    expect(canMoveUnder(find('ep'), find('ep'), rules, 'in').reason).toMatch(/under itself/);
    expect(canMoveUnder(find('ep'), find('st'), rules, 'in').reason).toMatch(/descendants/);
  });

  it('refuses a move to the parent it already has', () => {
    expect(canMoveUnder(find('ep'), find('in'), rules, 'in').reason).toMatch(/already under/);
  });

  it('refuses everything while the rules are not loaded', () => {
    expect(canMoveUnder(find('st'), find('ep2'), null, 'ep').ok).toBe(false);
  });
});
