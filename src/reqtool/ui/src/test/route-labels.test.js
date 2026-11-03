import { describe, it, expect, beforeEach } from 'vitest';
import { buildRoute, parseRoute, rememberedProduct, rememberProduct } from '../route';
import { labelOf } from '../labels';

describe('page addresses (#372)', () => {
  it('round-trips an area, tab, item, editor tab and product', () => {
    const route = { area: 'work', tab: 'backlog', item: 'u1', type: 'requirement', editorTab: 'relations', product: 'sensor_pro' };
    const hash = buildRoute(route);
    expect(hash).toBe('#/work/backlog?item=u1&tab=relations&product=sensor_pro');
    expect(parseRoute(hash)).toEqual({ ...route, type: 'requirement' });
  });

  it('leaves the default tab out of the address', () => {
    expect(buildRoute({ area: 'requirements', tab: 'tree' })).toBe('#/requirements');
    expect(parseRoute('#/requirements')).toMatchObject({ area: 'requirements', tab: 'tree', item: null });
  });

  it('falls back to Requirements for an unknown area and to the default tab for an unknown tab', () => {
    expect(parseRoute('#/nowhere/else')).toMatchObject({ area: 'requirements', tab: 'tree' });
    expect(parseRoute('#/insights/nope')).toMatchObject({ area: 'insights', tab: 'overview' });
  });

  it('reads old ?uid= links, sending decisions and principles to their areas', () => {
    expect(parseRoute('', '?uid=r1&type=requirement')).toMatchObject({ area: 'requirements', item: 'r1', type: 'requirement' });
    expect(parseRoute('', '?uid=d1&type=tbd')).toMatchObject({ area: 'decisions', item: 'd1', type: 'decision' });
    expect(parseRoute('', '?uid=p1&type=principle')).toMatchObject({ area: 'principles', item: 'p1' });
  });

  describe('remembered product', () => {
    beforeEach(() => localStorage.clear());
    it('is kept per repository', () => {
      rememberProduct('repo-a', 'p1');
      rememberProduct('repo-b', 'p2');
      expect(rememberedProduct('repo-a')).toBe('p1');
      expect(rememberedProduct('repo-b')).toBe('p2');
      rememberProduct('repo-a', null);
      expect(rememberedProduct('repo-a')).toBeNull();
    });
  });
});

describe('plain labels (#375)', () => {
  const hierarchy = {
    types: { bug: { label: 'Defect', workflow: 'sprint' }, issue: { label: 'Issue', workflow: 'triage' },
      functional: { label: 'Functional', workflow: 'formal', family: 'work' } },
    workflows: { triage: { states: [{ id: 'needs_info', label: 'Needs info' }, { id: 'fixing', label: 'Being fixed' }] } },
  };

  it('writes ids in sentence case', () => {
    expect(labelOf.plain('not_reproducible')).toBe('Not reproducible');
    expect(labelOf.plain('in_review')).toBe('In review');
    expect(labelOf.plain('Already Labelled')).toBe('Already Labelled');
  });

  it('takes status and type labels from the configuration', () => {
    expect(labelOf.status('fixing', 'issue', hierarchy)).toBe('Being fixed');
    expect(labelOf.status('in_progress', 'bug', hierarchy)).toBe('In progress');
    expect(labelOf.type('bug', hierarchy)).toBe('Defect');
    expect(labelOf.type('stakeholder_need', hierarchy)).toBe('Stakeholder need');
  });

  it('names links from each end', () => {
    expect(labelOf.link('derived_from')).toBe('Derived from');
    expect(labelOf.link('derived_from', true)).toBe('Source of');
    expect(labelOf.link('satisfies', true)).toBe('Satisfied by');
  });

  it('knows which family a type belongs to, and lets hierarchy.yaml choose', () => {
    expect(labelOf.family('story')).toBe('work');
    expect(labelOf.family('issue')).toBe('work');
    expect(labelOf.family('safety')).toBe('requirement');
    expect(labelOf.family('functional', hierarchy)).toBe('work');
  });
});
