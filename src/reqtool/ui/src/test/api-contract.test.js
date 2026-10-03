import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '../api';

function mockFetch() {
  global.fetch = vi.fn(() => Promise.resolve({
    ok: true, status: 200,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve({}),
  }));
}
const call = () => global.fetch.mock.calls[0];

describe('api contract (UI-10)', () => {
  beforeEach(() => { mockFetch(); localStorage.setItem('reqtool:username', 'alice'); });

  it('transition sends to_state', async () => {
    await api.requirements.transition('R-1', 'approved');
    expect(call()[0]).toContain('/requirements/R-1/transition');
    expect(JSON.parse(call()[1].body)).toEqual({ to_state: 'approved' });
  });

  it('reqif export uses GET', async () => {
    await api.exports.reqif();
    expect(call()[0]).toContain('/export/reqif');
    expect(call()[1].method).toBe('GET');
  });

  it('tbd resolve includes resolved_by', async () => {
    await api.tbds.resolve('T-1', { resolution: 'done' });
    expect(JSON.parse(call()[1].body)).toEqual({ resolved_by: 'alice', resolution: 'done' });
  });
});
