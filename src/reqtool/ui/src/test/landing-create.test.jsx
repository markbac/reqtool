vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { AppProvider, useApp } from '../AppContext';
import Editor from '../components/Editor.jsx';
import { quickTypes, templateBody } from '../createItem';

const ok = (body, status = 200) => Promise.resolve({
  ok: true, status, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)),
});

const HIERARCHY = {
  types: {
    theme: { label: 'Theme', icon: 'T', description: 'Strategic area' },
    epic: { label: 'Epic', icon: 'E', description: 'Capability' },
    functional: { label: 'Functional requirement', icon: 'F', description: 'The system shall' },
  },
  hierarchy: { theme: { allowed_children: ['epic'] }, epic: { allowed_children: [] } },
};
const TEMPLATE = { id: 'fr', label: 'Functional Requirement', description: 'A shall statement',
  fields: { req_type: 'functional', priority: 'high', content: { description: 'The system shall X', rationale: '' } } };

function Setup({ product = { id: 'prod' }, permissions = null }) {
  const { dispatch } = useApp();
  useEffect(() => {
    if (product) dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: product });
    dispatch({ type: 'SET_TEMPLATES', payload: [TEMPLATE] });
    if (permissions) dispatch({ type: 'SET_PERMISSIONS', payload: { permissions, role: 'viewer' } });
  }, [dispatch]);
  return null;
}

function Toasts() {
  const { state } = useApp();
  return <div>{state.toasts.map(t => <span key={t.id}>{t.message}</span>)}</div>;
}

function mount(props) {
  const calls = [];
  const events = [];
  window.addEventListener('reqtool:tree-changed', () => events.push('tree'));
  global.fetch = vi.fn((url, opts = {}) => {
    calls.push({ url: String(url), method: opts.method || 'GET', body: opts.body ? JSON.parse(opts.body) : null });
    if (String(url).endsWith('/hierarchy')) return ok(HIERARCHY);
    if ((opts.method || 'GET') === 'POST') return ok({ uid: 'new-uid', id: 'REQ-1' }, 201);
    return ok([]);
  });
  render(<AppProvider><Setup {...props} /><Toasts /><Editor /></AppProvider>);
  return { calls, events };
}

describe('landing page create buttons', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('quick create lists the repository types, top-level types first', async () => {
    mount({});
    await screen.findByTestId('quick-theme');
    const ids = screen.getAllByTestId(/^quick-/).map(b => b.dataset.testid);
    expect(ids).toEqual(['quick-functional', 'quick-theme', 'quick-epic']);
  });

  it('quick create makes the item, selects it and refreshes the tree', async () => {
    const { calls, events } = mount({});
    fireEvent.click(await screen.findByTestId('quick-epic'));
    await waitFor(() => expect(calls.some(c => c.method === 'POST')).toBe(true));
    const post = calls.find(c => c.method === 'POST');
    expect(post.body).toMatchObject({ req_type: 'epic', title: 'New Epic' });
    await waitFor(() => expect(events).toContain('tree'));
  });

  it('a template card creates the item straight away with the template fields', async () => {
    const { calls, events } = mount({});
    fireEvent.click(await screen.findByTestId('template-fr'));
    await waitFor(() => expect(calls.some(c => c.method === 'POST')).toBe(true));
    const post = calls.find(c => c.method === 'POST');
    expect(post.body.req_type).toBe('functional');
    expect(post.body.priority).toBe('high');
    expect(post.body.content.description).toBe('The system shall X');
    await waitFor(() => expect(events).toContain('tree'));
  });

  it('creates nothing without a product and says why', async () => {
    const { calls } = mount({ product: null });
    fireEvent.click(await screen.findByTestId('template-fr'));
    expect(await screen.findByText('Select a product first')).toBeTruthy();
    expect(calls.some(c => c.method === 'POST')).toBe(false);
  });

  it('a viewer sees no create buttons', async () => {
    mount({ permissions: ['read'] });
    await waitFor(() => expect(screen.queryByText('Quick create')).toBeNull());
    expect(screen.queryByTestId('template-fr')).toBeNull();
  });
});

describe('createItem helpers', () => {
  it('templateBody keeps template fields and always has content', () => {
    expect(templateBody({ label: 'X', fields: { priority: 'low' } }).content.description).toBe('The system shall...');
    expect(templateBody(TEMPLATE, 'p1')).toMatchObject({ parentId: 'p1', title: 'New Functional Requirement' });
  });

  it('quickTypes tolerates a missing hierarchy', () => {
    expect(quickTypes(null)).toEqual([]);
  });
});
