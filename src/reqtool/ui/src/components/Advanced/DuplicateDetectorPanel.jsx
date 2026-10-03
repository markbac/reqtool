import { useState, useEffect } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';

export function DuplicateDetectorPanel({ onClose }) {
  const { dispatch, toast } = useApp();
  const [threshold, setThreshold] = useState(0.7);
  const [duplicates, setDuplicates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const runDetection = async () => {
    setLoading(true);
    try {
      const res = await api.analysis.detectDuplicates(threshold);
      setDuplicates(Array.isArray(res) ? res : []);
      setSearched(true);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runDetection();
  }, []);

  const openReq = (uid) => {
    if (!uid) return;
    dispatch({ type: 'SELECT', uid, artefactType: 'requirement' });
    onClose();
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel side-panel--wide" onClick={e => e.stopPropagation()} style={{ width: 620 }}>
        <div className="side-panel-header">
          <span className="side-panel-title">AI Duplicate Detector</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div className="panel-body">
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16 }}>
            <label className="field-label" style={{ marginBottom: 0 }}>Similarity Threshold:</label>
            <input
              type="range"
              min="0.5"
              max="0.95"
              step="0.05"
              value={threshold}
              onChange={e => setThreshold(Number(e.target.value))}
            />
            <span className="mono" style={{ fontSize: 12, minWidth: 40 }}>{Math.round(threshold * 100)}%</span>
            <button className="btn btn-primary" onClick={runDetection} disabled={loading}>
              {loading ? <span className="spinner" /> : 'Re-scan'}
            </button>
          </div>

          {loading && <div className="panel-loading"><div className="spinner" /></div>}

          {!loading && searched && duplicates.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>
              ✓ No potential duplicates detected above {Math.round(threshold * 100)}% similarity threshold.
            </div>
          )}

          {!loading && duplicates.map((pair, idx) => (
            <div key={idx} style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: 12,
              marginBottom: 12
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="badge badge-warning">
                  Similarity: {Math.round((pair.similarity_score ?? 0) * 100)}%
                </span>
                <span className="text-muted" style={{ fontSize: 11 }}>Pair #{idx + 1}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div
                  onClick={() => openReq(pair.req_a.uid)}
                  style={{ cursor: 'pointer', padding: 8, background: 'var(--bg-primary)', borderRadius: 4, border: '1px solid var(--border)' }}
                >
                  <div className="mono" style={{ fontWeight: 600, fontSize: 11 }}>{pair.req_a.id}</div>
                  <div style={{ fontSize: 12, marginTop: 4 }}>{pair.req_a.title}</div>
                </div>

                <div
                  onClick={() => openReq(pair.req_b.uid)}
                  style={{ cursor: 'pointer', padding: 8, background: 'var(--bg-primary)', borderRadius: 4, border: '1px solid var(--border)' }}
                >
                  <div className="mono" style={{ fontWeight: 600, fontSize: 11 }}>{pair.req_b.id}</div>
                  <div style={{ fontSize: 12, marginTop: 4 }}>{pair.req_b.title}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
