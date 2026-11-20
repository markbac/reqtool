import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ResolveDialog from '../components/ResolveDialog.jsx';

const json = (body) => Promise.resolve({
  ok: true, status: 200, headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body),
});

describe('Accept decision dialog (MOD-16, #371)', () => {
  beforeEach(() => {
    global.fetch = vi.fn(() => json([{ uid: 'd1', id: 'DEC-1', title: 'Use MQTT', type: 'decision' },
                                     { uid: 't1', id: 'DEC-9', title: 'itself', type: 'decision' }]));
  });
  afterEach(() => vi.restoreAllMocks());

  it('cannot submit without a decision text', () => {
    render(<ResolveDialog tbd={{ uid: 't1', id: 'DEC-1', affected_requirements: [] }} onResolved={vi.fn()} onClose={() => {}} />);
    expect(screen.getByText('Accept decision', { selector: 'button' }).disabled).toBe(true);
  });

  it('sends decision, rationale and linked decision', async () => {
    const onResolved = vi.fn(() => Promise.resolve());
    render(<ResolveDialog tbd={{ uid: 't1', id: 'DEC-1', affected_requirements: ['a', 'b'] }} onResolved={onResolved} onClose={() => {}} />);
    expect(screen.getByText(/Requirements waiting on this \(2\)/)).toBeTruthy();
    await screen.findByText('DEC-1 -- Use MQTT');
    expect(screen.queryByText(/DEC-9/)).toBeNull(); // a decision is not offered as its own link
    fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'Use MQTT' } });
    fireEvent.change(screen.getByLabelText(/Rationale/), { target: { value: 'Already deployed' } });
    fireEvent.change(screen.getByLabelText(/Linked decision/), { target: { value: 'd1' } });
    fireEvent.click(screen.getByText('Accept decision', { selector: 'button' }));
    await waitFor(() => expect(onResolved).toHaveBeenCalledWith(
      { decision: 'Use MQTT', rationale: 'Already deployed', linked_decision: 'd1' }));
  });

  it('shows the server error and stays open', async () => {
    const onResolved = vi.fn(() => Promise.reject(new Error('A decision cannot be accepted without the decision text')));
    render(<ResolveDialog tbd={{ uid: 't1', id: 'DEC-1' }} onResolved={onResolved} onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'x' } });
    fireEvent.click(screen.getByText('Accept decision', { selector: 'button' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/cannot be accepted/);
  });
});
