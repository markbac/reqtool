import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ResolveDialog from '../components/ResolveDialog.jsx';

const json = (body) => Promise.resolve({
  ok: true, status: 200, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body),
});

describe('ResolveDialog (MOD-16)', () => {
  beforeEach(() => {
    global.fetch = vi.fn(() => json([{ uid: 'd1', id: 'DEC-1', title: 'Use MQTT', type: 'decision' },
                                     { uid: 't2', id: 'TBD-2', title: 'x', type: 'tbd' }]));
  });
  afterEach(() => vi.restoreAllMocks());

  it('cannot submit without a decision text', () => {
    render(<ResolveDialog tbd={{ id: 'TBD-1', affected_requirements: [] }} onResolved={vi.fn()} onClose={() => {}} />);
    expect(screen.getByText('Resolve', { selector: 'button' }).disabled).toBe(true);
  });

  it('sends decision, rationale and linked decision', async () => {
    const onResolved = vi.fn(() => Promise.resolve());
    render(<ResolveDialog tbd={{ id: 'TBD-1', affected_requirements: ['a', 'b'] }} onResolved={onResolved} onClose={() => {}} />);
    expect(screen.getByText(/Affected requirements \(2\)/)).toBeTruthy();
    await screen.findByText('DEC-1 -- Use MQTT');
    expect(screen.queryByText(/TBD-2/)).toBeNull(); // only decisions are offered as links
    fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'Use MQTT' } });
    fireEvent.change(screen.getByLabelText(/Rationale/), { target: { value: 'Already deployed' } });
    fireEvent.change(screen.getByLabelText(/Linked decision/), { target: { value: 'd1' } });
    fireEvent.click(screen.getByText('Resolve', { selector: 'button' }));
    await waitFor(() => expect(onResolved).toHaveBeenCalledWith(
      { decision: 'Use MQTT', rationale: 'Already deployed', linked_decision: 'd1' }));
  });

  it('shows the server error and stays open', async () => {
    const onResolved = vi.fn(() => Promise.reject(new Error('A TBD cannot be resolved without a decision text')));
    render(<ResolveDialog tbd={{ id: 'TBD-1' }} onResolved={onResolved} onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'x' } });
    fireEvent.click(screen.getByText('Resolve', { selector: 'button' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/without a decision/);
  });
});
