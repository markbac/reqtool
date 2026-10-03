import { describe, it, expect } from 'vitest';
import { buildBreadcrumb, MAX_CRUMB_DEPTH } from '../breadcrumb';

const mk = (map) => async (uid) => {
  if (!(uid in map)) throw new Error('404');
  return { uid, id: uid, title: uid, parentId: map[uid] };
};

describe('buildBreadcrumb (MOD-03)', () => {
  it('walks a normal chain root first', async () => {
    const crumbs = await buildBreadcrumb('b', mk({ b: 'a', a: null }), 'c');
    expect(crumbs.map(c => c.uid)).toEqual(['a', 'b']);
  });
  it('terminates on a cycle', async () => {
    const crumbs = await buildBreadcrumb('b', mk({ a: 'b', b: 'a' }), 'a');
    expect(crumbs.map(c => c.uid)).toEqual(['b']);
  });
  it('caps depth', async () => {
    const map = {};
    for (let i = 0; i < 200; i++) map['n' + i] = 'n' + (i + 1);
    const crumbs = await buildBreadcrumb('n0', mk(map));
    expect(crumbs.length).toBe(MAX_CRUMB_DEPTH);
  });
  it('stops at a missing parent', async () => {
    expect(await buildBreadcrumb('x', mk({}))).toEqual([]);
  });
});
