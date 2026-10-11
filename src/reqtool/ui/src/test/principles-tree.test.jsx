vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { useEffect } from 'react';
import { AppProvider, useApp } from '../AppContext';
import { PrinciplesPanel, PackDialog, PlacementFields } from '../components/Principles.jsx';

const ok = (body, status = 200) => Promise.resolve({
  ok: true, status, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)),
});

const ITEMS = [
  { uid: 'u1', id: 'P-ARCH-SEC-ONE', title: 'Defence in depth', area: 'architecture', category: 'security', status: 'draft' },
  { uid: 'u2', id: 'P-ARCH-STR-TWO', title: 'Layer rules', area: 'architecture', category: 'structure', status: 'approved', approval: { status: 'approved' } },
  { uid: 'u3', id: 'P-SEC-ID-THREE', title: 'Use MFA', area: 'security', category: 'identity', status: 'draft' },
  { uid: 'u4', id: 'P-MINE', title: 'Old one', status: 'draft' },
];
const TREE = {
  total: 4, unplaced: 1,
  areas: [
    { id: 'architecture', label: 'Architecture', count: 2, known: true, categories: [
      { id: 'structure', label: 'Structure and layering', count: 1 }, { id: 'security', label: 'Security', count: 1 }] },
    { id: 'security', label: 'Security', count: 1, known: true, categories: [{ id: 'identity', label: 'Identity and credentials', count: 1 }] },
  ],
};
const PACKS = [
  { area: 'security', label: 'Security', description: 'Credentials and more', count: 20, installed: 1, available: 19,
    categories: [{ id: 'identity', label: 'Identity and credentials', count: 5 }] },
  { area: 'business', label: 'Business', description: 'Why', count: 15, installed: 15, available: 0, categories: [] },
];
const VOCAB = { architecture: { label: 'Architecture', categories: { structure: { label: 'Structure' }, security: { label: 'Security' }, general: { label: 'General' } } },
                security: { label: 'Security', categories: { identity: { label: 'Identity' }, general: { label: 'General' } } } };

function Setup({ permissions }) {
  const { dispatch } = useApp();
  useEffect(() => {
    dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: { id: 'prod' } });
    if (permissions) dispatch({ type: 'SET_PERMISSIONS', payload: { permissions, role: 'x' } });
  }, [dispatch]);
  return null;
}
function Toasts() {
  const { state } = useApp();
  return <div>{state.toasts.map(t => <span key={t.id}>{t.message}</span>)}</div>;
}

let calls;
function mockApi({ items = ITEMS, packs = PACKS } = {}) {
  calls = [];
  global.fetch = vi.fn((url, opts = {}) => {
    const u = String(url), method = opts.method || 'GET';
    calls.push({ url: u, method, body: opts.body ? JSON.parse(opts.body) : null });
    if (u.includes('/principles/areas')) return ok(TREE);
    if (u.includes('/principles/packs/')) return ok({ area: u.split('/').pop(), added: 19, skipped: 1 });
    if (u.includes('/principles/packs')) return ok(packs);
    if (u.includes('/principles/vocabulary')) return ok(method === 'PUT' ? JSON.parse(opts.body) : { vocabulary: VOCAB, custom: true });
    if (u.match(/\/principles(\?|$)/) && method === 'GET') return ok(items);
    if (u.match(/\/principles\/u\d+$/) && method === 'PUT') return ok({ ...items[0], ...JSON.parse(opts.body) });
    if (u.endsWith('/principles') && method === 'POST') return ok({ uid: 'new', id: 'P-NEW' }, 201);
    return ok([]);
  });
}

const group = (area) => within(document.querySelector(`[data-area="${area}"]`));
const mount = (props = {}) => render(<AppProvider><Setup {...props} /><Toasts /><PrinciplesPanel /></AppProvider>);

describe('principles tree (PRN-03)', () => {
  beforeEach(() => { localStorage.clear(); mockApi(); });
  afterEach(() => vi.restoreAllMocks());

  it('shows areas first, then categories, then principles, all collapsed to start with', async () => {
    mount();
    expect(await screen.findByRole('button', { name: /Architecture/ })).toBeTruthy();
    expect(screen.queryByText('Defence in depth')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Architecture/ }));
    const cat = await group('architecture').findByRole('button', { name: /Security\s*1/ });
    expect(screen.queryByText('Defence in depth')).toBeNull();
    fireEvent.click(cat);
    expect(await screen.findByText('Defence in depth')).toBeTruthy();
    expect(screen.queryByText('Use MFA')).toBeNull();   // another area, still closed
  });

  it('counts include the unplaced group', async () => {
    mount();
    fireEvent.click(await screen.findByRole('button', { name: /Unplaced/ }));
    expect(screen.getByRole('button', { name: /No area/ })).toBeTruthy();
  });

  it('search opens every group that matches and hides the rest', async () => {
    mount();
    await screen.findByRole('button', { name: /Architecture/ });
    fireEvent.change(screen.getByLabelText('Search principles'), { target: { value: 'mfa' } });
    expect(await screen.findByText('Use MFA')).toBeTruthy();
    expect(screen.queryByText('Defence in depth')).toBeNull();
    expect(screen.queryByRole('button', { name: /Architecture/ })).toBeNull();
  });

  it('filters by status', async () => {
    mount();
    await screen.findByRole('button', { name: /Architecture/ });
    fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: 'approved' } });
    expect(await screen.findByText('Layer rules')).toBeTruthy();
    expect(screen.queryByText('Defence in depth')).toBeNull();
  });

  it('a new principle can be added inside a category', async () => {
    mount();
    fireEvent.click(await screen.findByRole('button', { name: /Architecture/ }));
    fireEvent.click(await screen.findByLabelText('New principle in Security'));
    await waitFor(() => expect(calls.some(c => c.method === 'POST' && c.url.endsWith('/principles'))).toBe(true));
    expect(calls.find(c => c.method === 'POST').body).toMatchObject({ area: 'architecture', category: 'security' });
  });

  it('dropping a principle on another category moves it', async () => {
    mount();
    fireEvent.click(await screen.findByRole('button', { name: /Architecture/ }));
    fireEvent.click(await group('architecture').findByRole('button', { name: /Security\s*1/ }));
    const row = (await screen.findByText('Defence in depth')).closest('.principle-row');
    const target = screen.getByRole('button', { name: /▸\s*Structure and layering/ }).closest('.principle-category-header');
    const data = {};
    const dataTransfer = { setData: (k, v) => { data[k] = v; }, getData: k => data[k] };
    fireEvent.dragStart(row, { dataTransfer });
    fireEvent.dragOver(target, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });
    await waitFor(() => expect(calls.some(c => c.method === 'PUT' && c.url.endsWith('/principles/u1'))).toBe(true));
    expect(calls.find(c => c.method === 'PUT' && c.url.endsWith('/principles/u1')).body).toEqual({ area: 'architecture', category: 'structure' });
  });

  it('a viewer sees the tree but no way to change it', async () => {
    mount({ permissions: ['read'] });
    fireEvent.click(await screen.findByRole('button', { name: /Architecture/ }));
    expect(screen.queryByText('+ New')).toBeNull();
    expect(screen.queryByText('+ Defaults')).toBeNull();
    expect(screen.queryByLabelText('New principle in Security')).toBeNull();
    fireEvent.click(await group('architecture').findByRole('button', { name: /Security\s*1/ }));
    expect((await screen.findByText('Defence in depth')).closest('.principle-row').getAttribute('draggable')).toBe('false');
  });

  it('only an administrator is offered the default packs', async () => {
    mount({ permissions: ['read', 'write'] });
    await screen.findByRole('button', { name: /Architecture/ });
    expect(screen.queryByText('+ Defaults')).toBeNull();
  });
});

describe('add default principles dialog', () => {
  beforeEach(() => { localStorage.clear(); mockApi(); });
  afterEach(() => vi.restoreAllMocks());

  it('lists packs with counts and adds only the chosen ones', async () => {
    const done = vi.fn(), close = vi.fn();
    render(<AppProvider><Toasts /><PackDialog onClose={close} onDone={done} /></AppProvider>);
    expect(await screen.findByText('1 of 20 in this repository')).toBeTruthy();
    expect(screen.getByLabelText('Business').disabled).toBe(true);   // nothing left to add
    const add = screen.getByRole('button', { name: /Add/ });
    expect(add.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('Security'));
    fireEvent.click(screen.getByRole('button', { name: /Add 1 pack/ }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const posts = calls.filter(c => c.method === 'POST');
    expect(posts.map(c => c.url.split('/').pop())).toEqual(['security']);
    expect(close).toHaveBeenCalled();
    expect(await screen.findByText('Added 19 principles')).toBeTruthy();
  });
});

describe('area and category selectors', () => {
  beforeEach(() => { localStorage.clear(); mockApi(); });
  afterEach(() => vi.restoreAllMocks());

  it('changing the area picks that area\'s general category', async () => {
    const change = vi.fn();
    render(<AppProvider><PlacementFields area="architecture" category="security" onChange={change} /></AppProvider>);
    await waitFor(() => expect(screen.getByLabelText('Area').options.length).toBeGreaterThan(2));
    fireEvent.change(screen.getByLabelText('Area'), { target: { value: 'security' } });
    expect(change).toHaveBeenCalledWith({ area: 'security', category: 'general' });
  });

  it('choosing a category keeps the area', async () => {
    const change = vi.fn();
    render(<AppProvider><PlacementFields area="architecture" category="security" onChange={change} /></AppProvider>);
    await waitFor(() => expect(screen.getByLabelText('Category').options.length).toBeGreaterThan(1));
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'structure' } });
    expect(change).toHaveBeenCalledWith({ area: 'architecture', category: 'structure' });
  });

  it('shows a value that is not in the vocabulary instead of hiding it', async () => {
    render(<AppProvider><PlacementFields area="elsewhere" category="x" onChange={() => {}} /></AppProvider>);
    expect(await screen.findByText('elsewhere (not in the vocabulary)')).toBeTruthy();
  });

  it('an administrator can add a category', async () => {
    const change = vi.fn();
    render(<AppProvider><PlacementFields area="architecture" category="security" onChange={change} /></AppProvider>);
    fireEvent.click(await screen.findByText('+ New category'));
    fireEvent.change(screen.getByLabelText('New category name'), { target: { value: 'Cost control' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(calls.some(c => c.method === 'PUT' && c.url.includes('/principles/vocabulary'))).toBe(true));
    const sent = calls.find(c => c.method === 'PUT').body.vocabulary;
    expect(sent.architecture.categories.cost_control.label).toBe('Cost control');
    await waitFor(() => expect(change).toHaveBeenCalledWith({ area: 'architecture', category: 'cost_control' }));
  });

  it('a viewer cannot add categories or change the selectors', async () => {
    const { container } = render(<AppProvider><Setup permissions={['read']} /><PlacementFields area="architecture" category="security" disabled onChange={() => {}} /></AppProvider>);
    await waitFor(() => expect(screen.getByLabelText('Area').disabled).toBe(true));
    expect(screen.queryByText('+ New category')).toBeNull();
    expect(container.querySelector('#principle-category').disabled).toBe(true);
  });
});
