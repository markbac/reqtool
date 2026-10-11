import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import {
  OverviewPanel, RoadmapPanel, DecisionsPanel, ModulesPanel, ChangeSetsPanel, QueryPanel, InboxPanel,
} from '../components/Insight';
import ItemInsight, { StatusStrip } from '../components/ItemInsight';
import { KanbanPanel } from '../components/Kanban';

const json = (body, status = 200) => Promise.resolve({
  ok: status < 400, status, statusText: 'x', headers: { get: () => 'application/json' }, json: () => Promise.resolve(body),
});

/** Route fetches by "METHOD /path-prefix" (first match wins); unknown routes return {}. */
function mockApi(routes) {
  global.fetch = vi.fn((url, opts = {}) => {
    const method = opts.method || 'GET';
    for (const [key, val] of Object.entries(routes)) {
      const [m, p] = key.split(' ');
      if (m === method && url.startsWith(p)) return typeof val === 'function' ? val(opts, url) : json(val);
    }
    return json({});
  });
}
const calls = (method, prefix) => global.fetch.mock.calls.filter(([u, o]) => (o?.method || 'GET') === method && u.startsWith(prefix));
const ui = (el) => render(<AppProvider>{el}</AppProvider>);

beforeEach(() => { localStorage.setItem('reqtool:username', 'alice'); });
afterEach(() => vi.restoreAllMocks());

describe('OverviewPanel (ENH-03, FEAT-01, FEAT-11, FEAT-12)', () => {
  const routes = {
    'GET /overview': { counts: { requirements: 12, modules: 2, products: 1, open_tbds: 3, decisions: 4 },
      by_status: { draft: 7, approved: 5 }, percentages: { approved: 41.7, verified: 25, traced: 80 },
      validation: { errors: 1, warnings: 6 }, baselines: ['baseline/v1'] },
    'GET /gate': { ready: false, count: 1, findings: [{ code: 'unverified_safety', uid: 'u1', id: 'FR-1', message: 'Safety-related item is not verified' }] },
    'GET /trend': { points: [{ baseline: 'v1', requirements: 10, approved_pct: 50, verified_pct: 20, traced_pct: 90, open_tbds: 2, churn: { added: 10, removed: 0, changed: 0 } }] },
    'GET /doctor': { ok: false, errors: 1, warnings: 0, checks: [{ level: 'error', code: 'secret_not_ignored', message: '.reqtool/.secret_key exists but is not in .gitignore' }] },
  };

  it('shows counts and percentages that match the API', async () => {
    mockApi(routes);
    ui(<OverviewPanel onClose={() => {}} />);
    expect(await screen.findByText('12')).toBeTruthy();
    expect(screen.getByText('42%')).toBeTruthy();
    expect(screen.getByRole('progressbar', { name: 'Verified' }).getAttribute('aria-valuenow')).toBe('25');
  });

  it('lists the gate findings and the health checks', async () => {
    mockApi(routes);
    ui(<OverviewPanel onClose={() => {}} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Release gate' }));
    expect(await screen.findByText(/1 finding\(s\) block the release/)).toBeTruthy();
    expect(screen.getByText('Safety-related item is not verified')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Health' }));
    expect(await screen.findByText(/not in .gitignore/)).toBeTruthy();
  });

  it('shows the trend per baseline', async () => {
    mockApi(routes);
    ui(<OverviewPanel onClose={() => {}} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Trend' }));
    expect(await screen.findByText('v1')).toBeTruthy();
    expect(screen.getByText('+10 -0 ~0')).toBeTruthy();
  });

  it('shows requirement coverage between two types', async () => {
    mockApi({ 'GET /traceability/matrix': { source_type: 'stakeholder_need', target_type: 'functional', total_sources: 2, covered_sources: 1, coverage_pct: 50,
      matrix: [{ source: { uid: 's1', id: 'SN-1', title: 'Need' }, targets: [{ uid: 'f1', id: 'FR-1' }] }, { source: { uid: 's2', id: 'SN-2', title: 'Other' }, targets: [] }] }, ...routes });
    ui(<OverviewPanel onClose={() => {}} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Coverage' }));
    expect(await screen.findByText('FR-1')).toBeTruthy();
    expect(screen.getByText('not covered')).toBeTruthy();
    expect(screen.getByText(/1 of 2 stakeholder_need items/)).toBeTruthy();
  });

  it('uploads JUnit results and reports what changed', async () => {
    mockApi({ 'POST /test-results': { tests: 3, updated: [{ uid: 'u1', id: 'FR-1', status: 'passed' }], unmatched_tests: ['x'] }, ...routes });
    ui(<OverviewPanel onClose={() => {}} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Test results' }));
    const file = new File(['<testsuite/>'], 'r.xml', { type: 'text/xml' });
    fireEvent.change(screen.getByLabelText('JUnit XML file'), { target: { files: [file] } });
    expect(await screen.findByText(/3 test\(s\): 1 requirement\(s\) updated, 1 matched no requirement/)).toBeTruthy();
  });
});

describe('RoadmapPanel (MOD-10, ENH-06)', () => {
  it('nests theme, initiative and epic with progress that matches the API', async () => {
    const node = (id, t, pct, children = []) => ({ uid: id, id, title: `${t} title`, req_type: t, status: 'active', progress_pct: pct,
      target_release: id === 'E-1' ? '2.0' : null, health: pct === 100 ? 'green' : 'amber', children });
    mockApi({ 'GET /roadmap': [node('T-1', 'theme', 25, [node('I-1', 'initiative', 40, [node('E-1', 'epic', 100)])])] });
    ui(<RoadmapPanel onClose={() => {}} />);
    expect(await screen.findByText('T-1')).toBeTruthy();
    expect(screen.getByText('E-1')).toBeTruthy();
    expect(screen.getByText('2.0')).toBeTruthy();
    expect(screen.getByRole('progressbar', { name: 'I-1 progress' }).getAttribute('aria-valuenow')).toBe('40');
  });
});

describe('DecisionsPanel (UI-06)', () => {
  it('creates a decision with options and an ATAM analysis', async () => {
    mockApi({ 'GET /decisions': [], 'POST /decisions': { uid: 'd1', id: 'DEC-1' } });
    ui(<DecisionsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByText('+ New decision'));
    fireEvent.change(screen.getByLabelText('Decision title'), { target: { value: 'Use MQTT' } });
    fireEvent.change(screen.getByLabelText('Options'), { target: { value: 'MQTT | + light; simple | - no queues\nAMQP | + rich | - heavy' } });
    fireEvent.click(screen.getByLabelText('ATAM analysis'));
    fireEvent.change(screen.getByLabelText('Sensitivity points'), { target: { value: 'latency: depends on the broker' } });
    fireEvent.change(screen.getByLabelText('Trade-off points'), { target: { value: 'latency+cost: cheaper brokers are slower' } });
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(calls('POST', '/decisions')).toHaveLength(1));
    const body = JSON.parse(calls('POST', '/decisions')[0][1].body);
    expect(body.title).toBe('Use MQTT');
    expect(body.content.options[0]).toEqual({ name: 'MQTT', pros: ['light', 'simple'], cons: ['no queues'] });
    expect(body.content.atam.sensitivity_points).toEqual([{ attribute: 'latency', description: 'depends on the broker' }]);
    expect(body.content.atam.tradeoff_points).toEqual([{ attributes: ['latency', 'cost'], description: 'cheaper brokers are slower' }]);
  });

  it('resolves a TBD to a decision', async () => {
    mockApi({ 'GET /decisions': [{ uid: 't1', id: 'TBD-1', title: 'Pick a bus', type: 'tbd', status: 'open' }],
      'POST /decisions/t1/resolve': { status: 'resolved' } });
    ui(<DecisionsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByText('Resolve', { selector: 'button' }));
    fireEvent.change(await screen.findByLabelText('Decision'), { target: { value: 'CAN' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByText('Resolve', { selector: 'button' }));
    await waitFor(() => expect(calls('POST', '/decisions/t1/resolve')).toHaveLength(1));
    expect(JSON.parse(calls('POST', '/decisions/t1/resolve')[0][1].body)).toEqual({ decision: 'CAN' });
  });
});

describe('ModulesPanel (UI-05, ENH-08, FEAT-08)', () => {
  const base = {
    'GET /modules/brakes/consumers': [{ product: 'car', title: 'Car', locked_version: '1.0.0' }],
    'GET /modules/brakes/verify': { verified: false, reason: 'hash mismatch' },
    'GET /modules/brakes': { manifest: { id: 'brakes', title: 'Brakes', version: '1.0.0', content: { description: 'ABS' },
      git_remote: 'https://example.com/b.git', git_ref: 'v1', pinned_commit: 'abcdef123456' }, requirements: [{ uid: 'r' }] },
    'GET /modules': [{ id: 'brakes', title: 'Brakes', version: '1.0.0' }],
  };

  it('shows a failed verification for a tampered module', async () => {
    mockApi(base);
    ui(<ModulesPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByText('Brakes'));
    expect(await screen.findByText('Car')).toBeTruthy();
    fireEvent.click(screen.getByText('Verify'));
    expect((await screen.findByRole('alert')).textContent).toBe('verification failed');
  });

  it('previews an update before it is accepted', async () => {
    mockApi({ 'GET /modules/brakes/update-preview': { added: ['c.yaml'], removed: [], changed: ['a.yaml'], consumers: [{}] }, ...base });
    ui(<ModulesPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByText('Brakes'));
    fireEvent.change(await screen.findByLabelText('Ref'), { target: { value: 'v2.0.0' } });
    fireEvent.click(screen.getByText('Preview update'));
    const region = await screen.findByRole('region', { name: 'Update preview' });
    expect(within(region).getByText(/added: c.yaml/)).toBeTruthy();
    expect(within(region).getByText(/changed: a.yaml/)).toBeTruthy();
    expect(within(region).getByText(/Affects 1 product/)).toBeTruthy();
  });

  it('bumps the version', async () => {
    mockApi({ 'POST /modules/brakes/version': { version: '1.1.0' }, ...base });
    ui(<ModulesPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByText('Brakes'));
    fireEvent.click(await screen.findByText('Bump minor'));
    await waitFor(() => expect(calls('POST', '/modules/brakes/version')).toHaveLength(1));
    expect(JSON.parse(calls('POST', '/modules/brakes/version')[0][1].body)).toEqual({ increment: 'minor' });
  });
});

describe('ChangeSetsPanel (FEAT-02)', () => {
  it('shows a field-level diff and merges only with a reviewer', async () => {
    mockApi({
      'GET /changesets/speed/diff': { name: 'speed', summary: { added: 1, removed: 0, modified: 1 },
        added: [{ path: 'a', id: 'FR-2', title: 'New' }], removed: [],
        modified: [{ path: 'b', id: 'FR-1', title: 'Old', fields: [{ field: 'title', old: 'Old', new: 'Newer' }] }] },
      'GET /changesets': [{ name: 'speed', branch: 'changeset/speed', base: 'main', current: true }],
      'POST /changesets/speed/merge': { merged: 'speed' },
    });
    vi.spyOn(window, 'prompt').mockReturnValue('dana');
    ui(<ChangeSetsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByText('Review'));
    const region = await screen.findByRole('region', { name: 'Change set diff' });
    expect(within(region).getByText(/1 added, 0 removed, 1 modified/)).toBeTruthy();
    expect(within(region).getByText('"Newer"', { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByText('Merge'));
    await waitFor(() => expect(calls('POST', '/changesets/speed/merge')).toHaveLength(1));
    expect(JSON.parse(calls('POST', '/changesets/speed/merge')[0][1].body)).toEqual({ reviewed_by: 'dana' });
  });
});

describe('QueryPanel (FEAT-09, UI-09)', () => {
  it('runs a query and persists a saved view to the repository', async () => {
    mockApi({ 'GET /query': { count: 1, results: [{ uid: 'u1', id: 'FR-1', title: 'Brake', status: 'approved' }] },
      'GET /filter-presets': [], 'PUT /filter-presets/': {} });
    vi.spyOn(window, 'prompt').mockReturnValue('Approved brakes');
    ui(<QueryPanel onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Query'), { target: { value: 'status:approved brake' } });
    fireEvent.click(screen.getByText('Run'));
    expect(await screen.findByText('FR-1')).toBeTruthy();
    expect(calls('GET', '/query')[0][0]).toBe('/query?q=status%3Aapproved%20brake');
    fireEvent.click(screen.getByText('Save view'));
    await waitFor(() => expect(calls('PUT', '/filter-presets/approved-brakes')).toHaveLength(1));
    expect(JSON.parse(calls('PUT', '/filter-presets/approved-brakes')[0][1].body)).toEqual({ label: 'Approved brakes', query: 'status:approved brake' });
  });

  it('shows the server message for a bad query', async () => {
    mockApi({ 'GET /query': () => json({ detail: { message: "'status:' has no value after the colon" } }, 422), 'GET /filter-presets': [] });
    ui(<QueryPanel onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Query'), { target: { value: 'status:' } });
    fireEvent.click(screen.getByText('Run'));
    expect((await screen.findByRole('alert')).textContent).toMatch(/no value after the colon/);
  });
});

describe('InboxPanel (FEAT-04, FEAT-10)', () => {
  it('lists notifications and flags a review request whose content changed', async () => {
    mockApi({
      'GET /reviews': [{ id: 'r1', uid: 'abcdef12345', requested_by: 'carol', status: 'stale' }],
      'GET /notifications/preferences/': { events: ['mention'], muted: false },
      'GET /notifications': [{ id: 'n1', uid: 'u1', text: 'carol mentioned @alice on FR-1', read: false, at: '2026-10-04T10:00:00Z' }],
    });
    ui(<InboxPanel onClose={() => {}} />);
    expect(await screen.findByText('carol mentioned @alice on FR-1')).toBeTruthy();
    expect(screen.getByText('changed since requested')).toBeTruthy();
    expect(screen.getByLabelText('mention')).toBeTruthy;
  });
});

describe('StatusStrip (UI-08)', () => {
  const strip = (git, isDirty) => {
    mockApi({ 'GET /git/status': git });
    return render(<AppProvider><StatusStrip uid="u1" isDirty={isDirty} version="1.2.0" /></AppProvider>);
  };

  it('moves through modified, saved, staged and committed', async () => {
    const a = strip({ staged: [], unstaged: [], untracked: [] }, true);
    expect(await screen.findByText('modified')).toBeTruthy();                       // editor: unsaved
    a.unmount();
    const b = strip({ staged: [], unstaged: ['requirements/u1.yaml'], untracked: [] }, false);
    await waitFor(() => expect(screen.getAllByText('modified').length).toBe(1));    // git: written to disk, not staged
    expect(screen.getByText('saved')).toBeTruthy();
    expect(screen.getByText(/next version is set when you commit/)).toBeTruthy();
    b.unmount();
    const c = strip({ staged: ['requirements/u1.yaml'], unstaged: [], untracked: [] }, false);
    expect(await screen.findByText('staged')).toBeTruthy();
    c.unmount();
    strip({ staged: [], unstaged: [], untracked: [] }, false);
    expect(await screen.findByText('clean')).toBeTruthy();                          // committed
    expect(screen.queryByText(/next version/)).toBeNull();
  });
});

describe('ItemInsight (ENH-01, ENH-02, ENH-05, FEAT-04, FEAT-06)', () => {
  const routes = {
    'GET /requirements/u1/trace': { uid: 'u1', gaps: ['no_downstream'], coverage: { children_verified_pct: 50 },
      upstream: [{ uid: 'p', id: 'P-1', title: 'Parent', relationship: 'satisfies', status: 'approved', suspect: true }],
      downstream: [], children: [{ uid: 'c', id: 'C-1', title: 'Child', status: 'draft' }] },
    'GET /requirements/u1/lifecycle': { stages: ['draft', 'review', 'approved', 'verified', 'baselined'], stage: 'review',
      blockers: [{ code: 'open_tbd', message: 'Open TBD TBD-1' }] },
    'GET /requirements/u1/progress': { progress_pct: 60 },
    'GET /requirements/u1/impact': {},
    'GET /requirements/u1/review-requests': [{ id: 'r1', reviewer: 'bob', version: '1.0.0', status: 'pending' }],
    'GET /requirements/u1/approvals': { approvals: [{ approved_by: 'carol', version: '1.0.0' }], current_hash: 'h1' },
    'POST /quality/check': { findings: [{ code: 'Q001', message: 'Replace vague wording: fast' }] },
    'POST /duplicates/suggest': { suggestions: [{ uid: 'd', id: 'FR-9', title: 'Similar', similarity_score: 0.62 }] },
    'POST /requirements/u1/review-requests': [{}],
    'POST /requirements/u1/approve': {},
  };
  const draft = { title: 'Brake fast', req_type: 'functional', content: { description: 'The system should be fast' } };

  it('shows the lifecycle strip, blockers, trace, suspect links and progress', async () => {
    mockApi(routes);
    ui(<ItemInsight uid="u1" draft={draft} version="1.0.0" />);
    expect(await screen.findByText('Open TBD TBD-1')).toBeTruthy();
    expect(screen.getByRole('list', { name: 'Lifecycle' }).querySelector('[aria-current="step"]').textContent).toBe('review');
    expect(screen.getByText('suspect')).toBeTruthy();
    expect(screen.getByText('P-1')).toBeTruthy();
    expect(screen.getByRole('progressbar', { name: 'Progress' }).getAttribute('aria-valuenow')).toBe('60');
  });

  it('shows advisory quality findings and similar items with an ignore action', async () => {
    mockApi(routes);
    ui(<ItemInsight uid="u1" draft={draft} version="1.0.0" />);
    expect(await screen.findByText('Replace vague wording: fast')).toBeTruthy();
    expect(await screen.findByText('FR-9')).toBeTruthy();
    fireEvent.click(screen.getByText('Ignore'));
    expect(screen.queryByText('FR-9')).toBeNull();
  });

  it('requests a review and approves the exact version shown', async () => {
    mockApi(routes);
    ui(<ItemInsight uid="u1" draft={draft} version="1.0.0" />);
    fireEvent.change(await screen.findByLabelText('Reviewers'), { target: { value: 'bob, carol' } });
    fireEvent.click(screen.getByText('Request review'));
    await waitFor(() => expect(calls('POST', '/requirements/u1/review-requests')).toHaveLength(1));
    expect(JSON.parse(calls('POST', '/requirements/u1/review-requests')[0][1].body)).toEqual({ reviewers: ['bob', 'carol'] });
    fireEvent.click(screen.getByText('Approve this version'));
    await waitFor(() => expect(calls('POST', '/requirements/u1/approve')).toHaveLength(1));
    expect(JSON.parse(calls('POST', '/requirements/u1/approve')[0][1].body)).toEqual({ approved_by: 'alice', content_hash: 'h1' });
  });

  it('shows a roll-up summary for a theme, initiative or epic', async () => {
    mockApi({ ...routes, 'GET /requirements/u1/summary': { progress_pct: 40, descendants: 5, done_estimate: 8, total_estimate: 20,
      open_tbds: ['TBD-1'], validation: { errors: 0, warnings: 2 }, by_type: { story: { done: 2, draft: 3 } } } });
    ui(<ItemInsight uid="u1" draft={{ ...draft, req_type: 'initiative' }} version="1.0.0" />);
    const region = await screen.findByRole('region', { name: 'Summary' });
    expect(within(region).getByText('40%')).toBeTruthy();
    expect(within(region).getByText('8/20')).toBeTruthy();
    expect(within(region).getByText('story')).toBeTruthy();
  });
});

describe('Kanban (MOD-13)', () => {
  it('shows cards that belong to no column in a visible lane', async () => {
    mockApi({ 'GET /kanban': { states: ['backlog', 'done'], req_type: null, columns: {
      backlog: [{ uid: 'a', id: 'S-1', title: 'A story', req_type: 'story' }], done: [],
      _uncolumned: [{ uid: 'b', id: 'F-1', title: 'Odd status', req_type: 'feature' }] } } });
    ui(<KanbanPanel />);
    expect(await screen.findByText('Odd status')).toBeTruthy();
    expect(screen.getByText('no matching column')).toBeTruthy();
    const options = [...screen.getByDisplayValue('All types').options].map(o => o.value);
    expect(options).not.toContain('theme');
    expect(options).not.toContain('initiative');
  });
});
