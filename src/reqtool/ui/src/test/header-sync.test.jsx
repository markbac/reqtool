vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import Header from '../components/Header.jsx';

const json = (body, status = 200) => Promise.resolve({
  ok: status < 400, status, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)),
});

const STATUS = { staged: [], unstaged: [], untracked: [],
  sync: { branch: 'main', upstream: 'origin/main', ahead: 2, behind: 1, remotes: ['origin'] } };

describe('Sync with a shared remote (#348)', () => {
  let calls;
  beforeEach(() => {
    calls = [];
    global.fetch = vi.fn((url, opts = {}) => {
      const path = new URL(url, 'http://localhost').pathname;
      calls.push(`${opts.method || 'GET'} ${path}`);
      if (path === '/git/status') return json(STATUS);
      if (path === '/git/sync') return json({ ...STATUS.sync, ahead: 0, behind: 0, changed: [], pushed: true,
        validation: { merge_errors: [], errors: 0, warnings: 0 } });
      return json([]);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it('shows ahead and behind counts and syncs on click', async () => {
    render(<AppProvider><Header /></AppProvider>);
    const button = await screen.findByTitle(/Sync with origin\/main/);
    expect(button).toHaveTextContent('↓1');
    expect(button).toHaveTextContent('↑2');
    const before = calls.filter(c => c === 'GET /git/status').length;
    fireEvent.click(button);
    await waitFor(() => expect(calls).toContain('POST /git/sync'));
    // nothing was pulled, so the status is refreshed rather than the page reloaded
    await waitFor(() => expect(calls.filter(c => c === 'GET /git/status').length).toBeGreaterThan(before));
  });

  it('is hidden without a remote', async () => {
    global.fetch = vi.fn(() => json({ staged: [], unstaged: [], untracked: [],
      sync: { branch: 'main', upstream: '', ahead: 0, behind: 0, remotes: [] } }));
    render(<AppProvider><Header /></AppProvider>);
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(screen.queryByTitle(/Sync with/)).not.toBeInTheDocument();
  });
});
