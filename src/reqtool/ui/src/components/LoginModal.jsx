/**
 * LoginModal.jsx -- Multi-user Login & Remote Server Connection Modal.
 */

import { useState, useEffect } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';

export function LoginModal({ onClose, onLoginSuccess }) {
  const { toast } = useApp();
  const [serverUrl, setServerUrl] = useState(localStorage.getItem('reqtool:server_url') || '');
  const [username, setUsername] = useState(localStorage.getItem('reqtool:username') || '');
  const [password, setPassword] = useState('');
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.auth.me()
      .then(u => setCurrentUser(u))
      .catch(() => setCurrentUser(null))
      .finally(() => setLoading(false));
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      // Save custom server URL if provided
      if (serverUrl.trim()) {
        localStorage.setItem('reqtool:server_url', serverUrl.trim());
      } else {
        localStorage.removeItem('reqtool:server_url');
      }

      const res = await api.auth.login(username.trim(), password.trim());
      localStorage.setItem('reqtool:auth_token', res.access_token);
      localStorage.setItem('reqtool:username', res.user.username);
      toast.success(`Logged in successfully as ${res.user.full_name || res.user.username}`);
      if (onLoginSuccess) onLoginSuccess(res.user);
      else window.location.reload();
      onClose();
    } catch (err) {
      setError(err.message || 'Login failed. Check server URL and credentials.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('reqtool:auth_token');
    toast.info('Logged out');
    setCurrentUser(null);
    window.location.reload();
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" style={{ maxWidth: 480 }} onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">🔐 Server Login & Connection</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        {loading ? (
          <div className="panel-loading"><div className="spinner" /></div>
        ) : (
          <div className="panel-body" style={{ padding: 16 }}>
            {currentUser && currentUser.authenticated && (
              <div style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 6,
                padding: 14,
                marginBottom: 16
              }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>
                  Active User: {currentUser.full_name || currentUser.username}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', margin: '4px 0 10px' }}>
                  Role: <span className="mono" style={{ color: 'var(--accent-color, #4ea8de)' }}>{currentUser.role}</span> | Username: <span className="mono">{currentUser.username}</span>
                </div>
                <button className="btn btn-danger" style={{ fontSize: 11 }} onClick={handleLogout}>
                  Logout
                </button>
              </div>
            )}

            {error && (
              <div style={{
                background: 'var(--danger-bg, #3d1c1c)',
                color: 'var(--danger-text, #ff8080)',
                padding: '8px 12px',
                borderRadius: 4,
                marginBottom: 12,
                fontSize: 12
              }}>
                ⚠️ {error}
              </div>
            )}

            <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span>Backend Server URL (optional for remote backend):</span>
                <input
                  type="url"
                  className="input-text mono"
                  value={serverUrl}
                  onChange={e => setServerUrl(e.target.value)}
                  placeholder="http://192.168.1.100:8765 (leave empty for local)"
                />
              </label>

              <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span>Username:</span>
                <input
                  type="text"
                  className="input-text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="e.g. admin or your username"
                  required
                />
              </label>

              <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span>Password:</span>
                <input
                  type="password"
                  className="input-text"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Enter password"
                  required
                />
              </label>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
                <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'Authenticating…' : 'Login'}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
