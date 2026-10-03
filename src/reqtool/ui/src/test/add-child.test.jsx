vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { AppProvider, useApp } from '../AppContext';
import Sidebar from '../components/Sidebar.jsx';

const ok = (body, status = 200) => Promise.resolve({
  ok: true, status, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)),
});

const TREE = [{ uid: 'p1', id: 'INI-1', title: 'Parent', req_type: 'initiative', children: [] }];

function Pick() {
  const { dispatch } = useApp();
  useEffect(() => { dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: { id: 'prod' } }); }, [dispatch]);
  return null;
}

async function setup(allowed) {
  const calls = [];
  global.fetch = vi.fn((url, opts = {}) => {
    calls.push({ url: String(url), method: opts.method || 'GET', body: opts.body ? JSON.parse(opts.body) : null });
    if (String(url).includes('/hierarchy/children/')) return ok({ allowed_children: allowed });
    if ((opts.method || 'GET') === 'POST') return ok({ uid: 'new', id: 'X-1' }, 201);
    if (String(url).includes('/tree')) return ok(TREE);
    return ok([]);
  });
  render(<AppProvider><Pick /><Sidebar tree={[]} principles={[]} tbds={[]} onRefresh={() => {}} /></AppProvider>);
  fireEvent.contextMenu(await screen.findByText('Parent'));
  fireEvent.click(screen.getByText('+ Add child'));
  return calls;
}

describe('add child follows the parent type (MOD-07)', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('creates the only allowed child type straight away', async () => {
    const calls = await setup(['epic']);
    await waitFor(() => expect(calls.some(c => c.method === 'POST' && c.url.endsWith('/requirements'))).toBe(true));
    const post = calls.find(c => c.method === 'POST' && c.url.endsWith('/requirements'));
    expect(calls.some(c => c.url.endsWith('/hierarchy/children/initiative'))).toBe(true);
    expect(post.body.req_type).toBe('epic');
    expect(post.body.parentId).toBe('p1');
  });

  it('offers a menu when several child types are allowed', async () => {
    const calls = await setup(['story', 'task']);
    const item = await screen.findByRole('menuitem', { name: /Task/ });
    expect(screen.getByRole('menuitem', { name: /Story/ })).toBeTruthy();
    fireEvent.click(item);
    await waitFor(() => expect(calls.some(c => c.method === 'POST')).toBe(true));
    expect(calls.find(c => c.method === 'POST').body.req_type).toBe('task');
  });
});
