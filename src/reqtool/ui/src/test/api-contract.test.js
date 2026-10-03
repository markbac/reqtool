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

describe('authentication handling (SEC-01)', () => {
  it('401 raises reqtool:unauthorized so the app can show the login dialog', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: false, status: 401, statusText: 'Unauthorized',
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ detail: { message: 'Authentication required' } }),
    }));
    const seen = vi.fn();
    window.addEventListener('reqtool:unauthorized', seen);
    await expect(api.requirements.list()).rejects.toThrow('Authentication required');
    expect(seen).toHaveBeenCalledTimes(1);
    window.removeEventListener('reqtool:unauthorized', seen);
  });

  it('a failed login does not trigger the login dialog event', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: false, status: 401, statusText: 'Unauthorized',
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ detail: 'Invalid username or password' }),
    }));
    const seen = vi.fn();
    window.addEventListener('reqtool:unauthorized', seen);
    await expect(api.auth.login('a', 'b')).rejects.toThrow('Invalid username or password');
    expect(seen).not.toHaveBeenCalled();
    window.removeEventListener('reqtool:unauthorized', seen);
  });

  it('audit package URL relies on the session cookie when same-origin', () => {
    localStorage.setItem('reqtool:auth_token', 'tok123');
    expect(api.exports.auditPackage({ a: '1' })).not.toContain('access_token');
  });

  it('audit package URL carries the token for a custom server', () => {
    localStorage.setItem('reqtool:server_url', 'http://other.example');
    localStorage.setItem('reqtool:auth_token', 'tok123');
    expect(api.exports.auditPackage({ a: '1' })).toContain('access_token=tok123');
    localStorage.removeItem('reqtool:server_url');
    localStorage.removeItem('reqtool:auth_token');
  });

  it('sends the CSRF header and never a stored token when same-origin', async () => {
    localStorage.setItem('reqtool:auth_token', 'stale');
    const f = vi.fn(() => Promise.resolve({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: () => Promise.resolve({}) }));
    vi.stubGlobal('fetch', f);
    await api.requirements.list();
    const h = f.mock.calls[0][1].headers;
    expect(h['X-Reqtool-CSRF']).toBe('1');
    expect(h.Authorization).toBeUndefined();
    localStorage.removeItem('reqtool:auth_token');
  });

  it('refreshes the session once on 401 and retries', async () => {
    const ok = { ok: true, status: 200, headers: { get: () => 'application/json' }, json: () => Promise.resolve({ ok: 1 }) };
    const f = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, statusText: 'x', headers: { get: () => 'application/json' }, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, status: 200 })   // /auth/refresh
      .mockResolvedValueOnce(ok);
    vi.stubGlobal('fetch', f);
    await expect(api.requirements.list()).resolves.toEqual({ ok: 1 });
    expect(f.mock.calls[1][0]).toContain('/auth/refresh');
    expect(f).toHaveBeenCalledTimes(3);
  });
});
