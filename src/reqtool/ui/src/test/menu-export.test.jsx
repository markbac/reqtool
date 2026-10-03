vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import Header from '../components/Header.jsx';
import { ExportPanel } from '../components/Panels.jsx';

const json = (body, status = 200) => Promise.resolve({
  ok: status < 400, status, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)),
});

describe('Templates menu entry (UI-02)', () => {
  beforeEach(() => { global.fetch = vi.fn(() => json([])); });
  afterEach(() => vi.restoreAllMocks());

  it('is in the overflow menu and calls onTemplates', () => {
    const onTemplates = vi.fn();
    render(<AppProvider><Header onTemplates={onTemplates} /></AppProvider>);
    fireEvent.click(screen.getByTitle('More tools'));
    fireEvent.click(screen.getByText(/Templates/));
    expect(onTemplates).toHaveBeenCalledTimes(1);
  });
});

describe('PDF export option (UI-04)', () => {
  const calls = [];
  beforeEach(() => {
    calls.length = 0;
    global.fetch = vi.fn((url, opts = {}) => {
      calls.push({ url: String(url), method: opts.method || 'GET' });
      return Promise.resolve({ ok: true, status: 200, headers: { get: () => 'application/pdf' },
        blob: () => Promise.resolve(new Blob(['%PDF-'], { type: 'application/pdf' })) });
    });
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());

  it('posts to /export/pdf and downloads the file', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<AppProvider><ExportPanel onClose={() => {}} /></AppProvider>);
    fireEvent.click(screen.getByLabelText('PDF'));
    fireEvent.click(screen.getByRole('button', { name: /Export PDF/ }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(calls.find(c => c.url.endsWith('/export/pdf')).method).toBe('POST');
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});
