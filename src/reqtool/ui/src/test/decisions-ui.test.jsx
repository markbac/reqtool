vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import { DecisionsPanel } from '../components/Sidebar.jsx';
import { KanbanPanel } from '../components/Kanban.jsx';

const json = (body) => Promise.resolve({
  ok: true, status: 200, headers: { get: () => 'application/json' }, json: () => Promise.resolve(body),
});

describe('DecisionsPanel (UI-06)', () => {
  let calls;
  beforeEach(() => {
    calls = [];
    global.fetch = vi.fn((url, opts) => {
      calls.push([String(url), opts?.method || 'GET']);
      if (String(url).includes('/export/adr')) {
        return Promise.resolve({ ok: true, status: 200, headers: { get: () => 'text/markdown' }, blob: () => Promise.resolve(new Blob(['# ADR'])) });
      }
      if (String(url).startsWith('/decisions') && opts?.method === 'POST') return json({ uid: 'new1', id: 'DEC-1' });
      return json([{ uid: 'd1', id: 'DEC-0001', title: 'Use REST', status: 'accepted', type: 'decision' }]);
    });
    global.URL.createObjectURL = vi.fn(() => 'blob:x');
    global.URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());

  it('lists decisions only, creates one and exports the ADR', async () => {
    render(<AppProvider><DecisionsPanel /></AppProvider>);
    expect(await screen.findByText('Use REST')).toBeTruthy();
    expect(calls[0][0]).toContain('/decisions?type=decision');
    fireEvent.click(screen.getByText('+ New'));
    await waitFor(() => expect(calls.some(([u, m]) => u === '/decisions' && m === 'POST')).toBe(true));
    fireEvent.click(screen.getByText('Export ADR'));
    await waitFor(() => expect(calls.some(([u]) => u.includes('/export/adr'))).toBe(true));
  });
});

describe('Kanban (MOD-13)', () => {
  beforeEach(() => {
    global.fetch = vi.fn(() => json({
      states: ['backlog', 'done'], delivery_types: ['epic', 'story'],
      columns: { backlog: [{ uid: 'a', id: 'US-1', title: 'In column', req_type: 'story' }],
                 done: [], _uncolumned: [{ uid: 'b', id: 'US-2', title: 'Lost card', req_type: 'story' }] },
    }));
  });
  afterEach(() => vi.restoreAllMocks());

  it('shows cards that match no column in a visible lane', async () => {
    render(<AppProvider><KanbanPanel /></AppProvider>);
    expect(await screen.findByText('Lost card')).toBeTruthy();
    expect(screen.getByText('no matching column')).toBeTruthy();
  });

  it('offers delivery types only in the type filter', async () => {
    render(<AppProvider><KanbanPanel /></AppProvider>);
    await screen.findByText('In column');
    const options = [...document.querySelectorAll('.kanban-select option')].map(o => o.textContent);
    expect(options).toContain('Story');
    expect(options).not.toContain('Theme');
    expect(options).not.toContain('Initiative');
  });
});
