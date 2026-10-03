vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import { CoveragePanel } from '../components/Tools.jsx';

const json = (body) => Promise.resolve({
  ok: true, status: 200, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)),
});

describe('CoveragePanel (PERF-06)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('uses /metrics and does not download the requirement list', async () => {
    const urls = [];
    global.fetch = vi.fn((url) => {
      urls.push(String(url));
      return json({
        totals: { requirements: 10 }, status: { approved: 4, draft: 6 }, priority: { high: 10 },
        quality_gaps: { no_ac: 3, no_owner: 2, not_verified: 5, no_rationale: 1 },
      });
    });
    render(<AppProvider><CoveragePanel onClose={() => {}} /></AppProvider>);
    expect(await screen.findByText('10 requirements')).toBeTruthy();
    expect(screen.getByText('No acceptance criteria').parentElement.textContent).toMatch(/3/);
    expect(urls.some(u => u.endsWith('/metrics'))).toBe(true);
    expect(urls.some(u => u.includes('/requirements'))).toBe(false);
  });
});
