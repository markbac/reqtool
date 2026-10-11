import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import { ViewsPanel, RoadmapBoard, TraceGrid } from '../components/Views';

const json = (body, status = 200) => Promise.resolve({
  ok: status < 400, status, statusText: 'x', headers: { get: () => 'application/json' }, json: () => Promise.resolve(body),
});
function mockApi(routes) {
  global.fetch = vi.fn((url, opts = {}) => {
    const method = opts.method || 'GET';
    for (const [key, val] of Object.entries(routes)) {
      const [m, p] = key.split(' ');
      if (m === method && url.startsWith(p)) return json(val);
    }
    return json({});
  });
}
const ui = (el) => render(<AppProvider>{el}</AppProvider>);
beforeEach(() => { localStorage.setItem('reqtool:username', 'alice'); });
afterEach(() => vi.restoreAllMocks());

const node = (uid, id, depth, parent, children = 0) => ({ uid, id, title: `Title ${id}`, type: 'story', status: 'draft', status_label: 'Draft', colour: '#888', parent, depth, children, match: true });

describe('Views panel', () => {
  it('collapses a branch of the hierarchy and says when the tree was cut', async () => {
    mockApi({ 'GET /views/hierarchy': { nodes: [node('a', 'EP-1', 0, null, 1), node('b', 'US-1', 1, 'a')], shown: 2, total: 9, matched: 2, capped: true } });
    ui(<ViewsPanel onClose={() => {}} />);
    expect((await screen.findAllByRole('treeitem')).length).toBe(2);
    expect(screen.getByRole('status').textContent).toMatch(/Showing 2 of 9/);
    fireEvent.click(screen.getByRole('button', { name: 'Collapse EP-1' }));
    expect(screen.getAllByRole('treeitem').length).toBe(1);
    fireEvent.click(screen.getByRole('button', { name: 'Expand EP-1' }));
    expect(screen.getAllByRole('treeitem').length).toBe(2);
  });

  it('shows an empty message and a table form of coverage', async () => {
    mockApi({
      'GET /views/hierarchy': { nodes: [], shown: 0, total: 0, matched: 0, capped: false },
      'GET /views/coverage': { by: 'status', roots: [{ uid: 'a', id: 'EP-1', title: 'Epic', type: 'epic', status: 'draft', count: 2, by: { draft: 2 }, children: [] }], totals: { draft: 2 }, colours: { draft: '#888' }, total: 2 },
    });
    ui(<ViewsPanel onClose={() => {}} />);
    expect(await screen.findByTestId('view-empty')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Coverage' }));
    expect(await screen.findByTestId('coverage-cell')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show table' }));
    expect(screen.getByTestId('coverage-table').textContent).toMatch(/EP-1/);
  });

  it('flags stuck items in the flow funnel', async () => {
    mockApi({
      'GET /views/hierarchy': { nodes: [], shown: 0, total: 0, capped: false },
      'GET /views/flow': { stuck_days: 14, workflows: [{ workflow: 'sprint', types: ['story'], total: 3, initial: 'backlog', transitions: {}, states: [
        { state: 'backlog', label: 'Backlog', colour: '#888', terminal: false, count: 3, avg_days: 20, max_days: 30, threshold: 14, stuck_count: 2, stuck: [{ uid: 'a', id: 'US-1', title: 't', days: 30 }] }] }] },
    });
    ui(<ViewsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Flow' }));
    expect(await screen.findByText('2 stuck')).toBeTruthy();
  });
});

describe('Roadmap board', () => {
  const board = { group_by: 'release', columns: ['R1', 'unplanned'], lanes: [{ uid: 'l', id: 'TH-1', title: 'Theme', progress_pct: 10, health: 'green' }],
    cards: [{ uid: 'c', id: 'IN-1', title: 'Init', lane: 'l', column: 'R1', progress_pct: 40, status: 'draft' }], needs: [], dependencies: [], critical_chain: [] };

  it('lets an editor re-plan a card from its menu', async () => {
    mockApi({ 'GET /roadmap/board': board, 'PUT /requirements/c': {} });
    ui(<RoadmapBoard open={() => {}} canEdit />);
    fireEvent.change(await screen.findByLabelText('Move IN-1 to'), { target: { value: 'unplanned' } });
    await waitFor(() => {
      const put = global.fetch.mock.calls.find(([, o]) => o?.method === 'PUT');
      expect(JSON.parse(put[1].body)).toEqual({ target_release: null });
    });
  });

  it('is read-only for a viewer', async () => {
    mockApi({ 'GET /roadmap/board': board });
    ui(<RoadmapBoard open={() => {}} canEdit={false} />);
    expect(await screen.findByText('Init')).toBeTruthy();
    expect(screen.queryByLabelText('Move IN-1 to')).toBeNull();
    expect(screen.getByText(/Read-only/)).toBeTruthy();
  });
});

describe('Traceability grid', () => {
  it('tells the person what is missing and offers a CSV', async () => {
    mockApi({ 'GET /traceability/grid': { columns_kind: 'tests', columns: [{ key: 'T-1', count: 1 }], columns_total: 1, total: 2, offset: 0, limit: 50, all_requirements: 2, without_links: 1,
      rows: [{ uid: 'a', id: 'FR-1', title: 'One', linked: 1, cells: { 'T-1': { state: 'passed' } } }, { uid: 'b', id: 'FR-2', title: 'Two', linked: 0, cells: {} }] } });
    ui(<TraceGrid product="p1" />);
    expect(await screen.findByText('no link')).toBeTruthy();
    expect(screen.getByRole('status').textContent).toMatch(/1 of 2 have no test link/);
    expect(screen.getByRole('link', { name: 'Download CSV' }).getAttribute('href')).toMatch(/format=csv/);
  });
});
