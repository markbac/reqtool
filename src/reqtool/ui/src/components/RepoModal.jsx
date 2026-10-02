/**
 * RepoModal.jsx -- Modal for switching active repository or initializing a new repository.
 */

import { useState, useEffect } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';

export function RepoModal({ onClose, onRepoChanged }) {
  const { toast } = useApp();
  const [tab, setTab] = useState('switch'); // 'switch' | 'init'
  const [repoInfo, setRepoInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Switch form state
  const [switchPath, setSwitchPath] = useState('');

  // Init form state
  const [initPath, setInitPath] = useState('');
  const [initRepoId, setInitRepoId] = useState('');
  const [initTitle, setInitTitle] = useState('');
  const [initMode, setInitMode] = useState('defaults');

  // Edit Details state
  const [editTitle, setEditTitle] = useState('');
  const [editDesc, setEditDesc] = useState('');

  useEffect(() => {
    api.repo.get()
      .then(info => {
        setRepoInfo(info);
        setSwitchPath(info.path || '');
        setEditTitle(info.repo_title || '');
        setEditDesc(info.repo_description || '');
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSaveDetails = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.config.update({ repo_title: editTitle.trim(), repo_description: editDesc.trim() });
      toast.success('Repository title and overarching description updated!');
      const updatedInfo = await api.repo.get();
      setRepoInfo(updatedInfo);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };


  const handleSwitch = async (e) => {
    e.preventDefault();
    if (!switchPath.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.repo.switch(switchPath.trim());
      toast.success(`Switched repository to: ${res.repo_title || res.repo_id}`);
      if (onRepoChanged) onRepoChanged();
      else window.location.reload();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleInit = async (e) => {
    e.preventDefault();
    if (!initPath.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.repo.init({
        path: initPath.trim(),
        repo_id: initRepoId.trim() || undefined,
        title: initTitle.trim() || undefined,
        mode: initMode,
      });
      toast.success(`Initialized and loaded repository: ${res.repo_title || res.repo_id}`);
      if (onRepoChanged) onRepoChanged();
      else window.location.reload();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" style={{ maxWidth: 540 }} onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">📦 Repository Management</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        {loading ? (
          <div className="panel-loading"><div className="spinner" /></div>
        ) : (
          <div className="panel-body" style={{ padding: 16 }}>
            {/* Active Repo Info Card */}
            {repoInfo && (
              <div style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 6,
                padding: '12px 14px',
                marginBottom: 16
              }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>
                  Active: {repoInfo.repo_title} <span className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>({repoInfo.repo_id})</span>
                </div>
                <div className="mono" style={{ fontSize: 11, color: 'var(--text-muted)', margin: '4px 0 8px', wordBreak: 'break-all' }}>
                  {repoInfo.path}
                </div>
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-secondary)' }}>
                  <span>📋 {repoInfo.requirements_count} requirements</span>
                  <span>💡 {repoInfo.principles_count} principles</span>
                  <span>❓ {repoInfo.tbds_count} TBDs</span>
                </div>
              </div>
            )}

            {/* Sub-navigation tabs */}
            <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid var(--border-color)', marginBottom: 16 }}>
              <button
                className={`btn ${tab === 'details' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ borderRadius: '4px 4px 0 0', fontSize: 12 }}
                onClick={() => { setTab('details'); setError(null); }}
              >
                Repo Details & Description
              </button>
              <button
                className={`btn ${tab === 'switch' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ borderRadius: '4px 4px 0 0', fontSize: 12 }}
                onClick={() => { setTab('switch'); setError(null); }}
              >
                Switch Repository
              </button>
              <button
                className={`btn ${tab === 'init' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ borderRadius: '4px 4px 0 0', fontSize: 12 }}
                onClick={() => { setTab('init'); setError(null); }}
              >
                Init New Repository
              </button>
            </div>

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

            {tab === 'details' ? (
              <form onSubmit={handleSaveDetails} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span>Repository Title:</span>
                  <input
                    type="text"
                    className="input-text"
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    placeholder="e.g. IoT Environmental Sensor Platform"
                    required
                  />
                </label>

                <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span>Overarching Repository Description (Start of PDF Export):</span>
                  <textarea
                    className="input-text"
                    rows={5}
                    value={editDesc}
                    onChange={e => setEditDesc(e.target.value)}
                    placeholder="Enter an overarching summary of this repository, its architecture, business goals, and operational scope..."
                    style={{ resize: 'vertical' }}
                  />
                </label>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
                  <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
                  <button type="submit" className="btn btn-primary" disabled={submitting}>
                    {submitting ? 'Saving…' : 'Save Details'}
                  </button>
                </div>
              </form>
            ) : tab === 'switch' ? (
              <form onSubmit={handleSwitch} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span>Target Repository Path:</span>
                  <input
                    type="text"
                    className="input-text mono"
                    value={switchPath}
                    onChange={e => setSwitchPath(e.target.value)}
                    placeholder="e.g. C:\projects\my-req-repo"
                    required
                  />
                </label>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
                  <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
                  <button type="submit" className="btn btn-primary" disabled={submitting}>
                    {submitting ? 'Switching…' : 'Switch Repository'}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleInit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span>New Repository Directory Path:</span>
                  <input
                    type="text"
                    className="input-text mono"
                    value={initPath}
                    onChange={e => setInitPath(e.target.value)}
                    placeholder="e.g. C:\projects\new-product-reqs"
                    required
                  />
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span>Repo ID (slug):</span>
                    <input
                      type="text"
                      className="input-text"
                      value={initRepoId}
                      onChange={e => setInitRepoId(e.target.value)}
                      placeholder="e.g. medical-device-v1"
                    />
                  </label>
                  <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span>Repo Title:</span>
                    <input
                      type="text"
                      className="input-text"
                      value={initTitle}
                      onChange={e => setInitTitle(e.target.value)}
                      placeholder="e.g. Medical Device V1"
                    />
                  </label>
                </div>

                <label style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span>Template & Scaffold Mode:</span>
                  <select
                    className="header-select"
                    value={initMode}
                    onChange={e => setInitMode(e.target.value)}
                  >
                    <option value="defaults">Engineering Defaults (Principles + Enums + Workflows)</option>
                    <option value="blank">Blank Repository</option>
                  </select>
                </label>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
                  <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
                  <button type="submit" className="btn btn-primary" disabled={submitting}>
                    {submitting ? 'Initializing…' : 'Initialize Repository'}
                  </button>
                </div>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
