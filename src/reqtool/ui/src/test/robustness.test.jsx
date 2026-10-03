vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import ErrorBoundary from '../components/ErrorBoundary.jsx';
import { IterationsPanel } from '../components/IterationsPanel.jsx';
import { DuplicateDetectorPanel } from '../components/Advanced/DuplicateDetectorPanel.jsx';

const json = (body) => Promise.resolve({
  ok: true, status: 200, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)),
});

describe('ErrorBoundary (UI-14)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows a recoverable fallback instead of a blank page', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const onReset = vi.fn();
    let boom = true;
    const Bomb = () => { if (boom) throw new Error('kaboom'); return <div>fine</div>; };
    render(<ErrorBoundary onReset={onReset}><Bomb /></ErrorBoundary>);
    expect(screen.getByRole('alert').textContent).toMatch(/kaboom/);
    boom = false;
    fireEvent.click(screen.getByText('Try again'));
    expect(onReset).toHaveBeenCalled();
    expect(screen.getByText('fine')).toBeTruthy();
  });
});

describe('IterationsPanel (UI-14)', () => {
  beforeEach(() => { global.fetch = vi.fn(() => json([{ id: 's1', title: 'S', status: 'planned' }])); });
  afterEach(() => vi.restoreAllMocks());

  it('renders an iteration that has no methodology', async () => {
    render(<AppProvider><IterationsPanel onClose={() => {}} /></AppProvider>);
    expect(await screen.findByText('SCRUM')).toBeTruthy();
  });
});

describe('DuplicateDetectorPanel (UI-13)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows both IDs and titles from the real response shape', async () => {
    global.fetch = vi.fn(() => json([{
      req_a: { uid: 'ua', id: 'REQ-1', title: 'Alpha' },
      req_b: { uid: 'ub', id: 'REQ-2', title: 'Beta' },
      similarity_score: 0.82, overlapping_terms: ['x'],
    }]));
    render(<AppProvider><DuplicateDetectorPanel onClose={() => {}} /></AppProvider>);
    expect(await screen.findByText('REQ-1')).toBeTruthy();
    expect(screen.getByText('REQ-2')).toBeTruthy();
    expect(screen.getByText('Alpha')).toBeTruthy();
    expect(screen.getByText(/82%/)).toBeTruthy();
  });

  it('clicking a card opens that item and closes the panel', async () => {
    global.fetch = vi.fn(() => json([{
      req_a: { uid: 'ua', id: 'REQ-1', title: 'Alpha' },
      req_b: { uid: 'ub', id: 'REQ-2', title: 'Beta' },
      similarity_score: 0.9,
    }]));
    const onClose = vi.fn();
    render(<AppProvider><DuplicateDetectorPanel onClose={onClose} /></AppProvider>);
    fireEvent.click(await screen.findByText('Beta'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
