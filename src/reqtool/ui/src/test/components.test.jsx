/**
 * components.test.jsx
 *
 * Smoke tests for Header, Sidebar, Editor, App.
 *
 * vi.mock() calls are hoisted to the top of the transformed file by Vitest,
 * so they intercept the import before the module graph is resolved.
 * This is how we prevent @uiw/react-codemirror from bringing in a
 * second React copy at static import time.
 */

// IMPORTANT: vi.mock() must appear before any imports for hoisting to work.
// Vitest transforms the file and moves vi.mock() calls to the very top.
vi.mock('@uiw/react-codemirror', () => ({
  default: ({ value, onChange }) =>
    <textarea data-testid="codemirror" value={value ?? ''} onChange={e => onChange?.(e.target.value)} />,
}));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import Header from '../components/Header.jsx';
import Sidebar from '../components/Sidebar.jsx';
import Editor from '../components/Editor.jsx';
import App from '../App.jsx';

// ---------------------------------------------------------------------------
// API mock
// ---------------------------------------------------------------------------

const EMPTY = {
  '/enums':        { domain: [], discipline: [], team: [], owner: [], tags: [], nfr_keys: [], estimate_unit: 'points' },
  '/workflow':     { states: [], transitions: {} },
  '/templates':    [],
  '/products':     [],
  '/requirements': { items: [], total: 0 },
  '/principles':   { items: [], total: 0 },
  '/tbds':         { items: [], total: 0 },
  '/git/status':   { staged: [], unstaged: [], untracked: [] },
  '/health':       { status: 'ok' },
  '/hierarchy':    { types: {}, hierarchy: {}, workflows: {}, dor: {}, dod: {}, cross_layer_rules: [] },
};

function makeFetch() {
  return vi.fn(url => {
    const path = new URL(url, 'http://localhost').pathname;
    return Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve(EMPTY[path] ?? {}),
      text: () => Promise.resolve(JSON.stringify(EMPTY[path] ?? {})),
    });
  });
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

describe('Header', () => {
  beforeEach(() => { global.fetch = makeFetch(); });
  afterEach(() => vi.restoreAllMocks());

  it('renders without throwing', () => {
    expect(() =>
      render(<AppProvider><Header onToggleSidebar={() => {}} /></AppProvider>)
    ).not.toThrow();
  });

  it('produces non-empty DOM', () => {
    render(<AppProvider><Header onToggleSidebar={() => {}} /></AppProvider>);
    expect(document.body.innerHTML.length).toBeGreaterThan(20);
  });

  it('contains at least one button', () => {
    render(<AppProvider><Header onToggleSidebar={() => {}} /></AppProvider>);
    expect(document.querySelectorAll('button').length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

describe('Sidebar', () => {
  beforeEach(() => { global.fetch = makeFetch(); });
  afterEach(() => vi.restoreAllMocks());

  it('renders without throwing', () => {
    expect(() =>
      render(<AppProvider>
        <Sidebar tree={[]} principles={[]} tbds={[]} onRefresh={() => {}} />
      </AppProvider>)
    ).not.toThrow();
  });

  it('renders Requirements, Principles, TBDs tabs', () => {
    render(<AppProvider>
      <Sidebar tree={[]} principles={[]} tbds={[]} onRefresh={() => {}} />
    </AppProvider>);
    // Use getAllByText since "Requirements" may appear in both tab and empty-state text
    expect(screen.getAllByText(/requirements/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/principles/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/tbd/i).length).toBeGreaterThan(0);
  });

  it('shows non-empty DOM when tree is empty', () => {
    render(<AppProvider>
      <Sidebar tree={[]} principles={[]} tbds={[]} onRefresh={() => {}} />
    </AppProvider>);
    expect(document.body.textContent.length).toBeGreaterThan(5);
  });
});

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------

describe('Editor', () => {
  beforeEach(() => { global.fetch = makeFetch(); });
  afterEach(() => vi.restoreAllMocks());

  it('renders empty state without throwing', () => {
    expect(() =>
      render(<AppProvider>
        <Editor uid={null} artefactType={null} onSaved={() => {}} onDeleted={() => {}} />
      </AppProvider>)
    ).not.toThrow();
  });

  it('produces DOM output when uid is null', () => {
    render(<AppProvider>
      <Editor uid={null} artefactType={null} onSaved={() => {}} onDeleted={() => {}} />
    </AppProvider>);
    expect(document.body.children.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// App (full mount)
// ---------------------------------------------------------------------------

describe('App', () => {
  beforeEach(() => {
    global.fetch = makeFetch();
    global.WebSocket = vi.fn(() => ({
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      close: vi.fn(),
      readyState: 1,
    }));
  });
  afterEach(() => vi.restoreAllMocks());

  it('mounts without a useContext null error', async () => {
    const errors = [];
    const orig = console.error.bind(console);
    console.error = (...a) => {
      const m = a.join(' ');
      if (m.includes('useContext') && m.includes('null')) errors.push(m);
      if (!m.includes('act(') && !m.includes('Warning:')) orig(...a);
    };
    await act(async () => { render(<App />); });
    expect(errors).toHaveLength(0);
    console.error = orig;
  });

  it('does not throw on initial render', async () => {
    let threw = false;
    try { await act(async () => { render(<App />); }); }
    catch { threw = true; }
    expect(threw).toBe(false);
  });

  it('renders meaningful DOM content', async () => {
    await act(async () => { render(<App />); });
    expect(document.body.innerHTML.length).toBeGreaterThan(100);
  });
});
