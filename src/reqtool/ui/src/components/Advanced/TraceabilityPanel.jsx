import { useState, useEffect } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';

export function TraceabilityPanel({ onClose }) {
  const { state } = useApp();
  const { activeProduct } = state;
  const [matrix, setMatrix] = useState(null);
  const [loading, setLoading] = useState(true);
  const [relFilter, setRelFilter] = useState({ requires: true, derived_from: true, satisfies: true });

  useEffect(() => {
    if (!activeProduct) { setLoading(false); return; }
    api.products.matrix(activeProduct.id)
      .then(setMatrix)
      .catch(() => setMatrix(null))
      .finally(() => setLoading(false));
  }, [activeProduct]);

  const toggleRel = (key) => setRelFilter(f => ({ ...f, [key]: !f[key] }));

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="wide-panel" onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">Traceability Matrix & Dependency Filters</span>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
              <input type="checkbox" checked={relFilter.requires} onChange={() => toggleRel('requires')} /> requires
            </label>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
              <input type="checkbox" checked={relFilter.derived_from} onChange={() => toggleRel('derived_from')} /> derived_from
            </label>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
              <input type="checkbox" checked={relFilter.satisfies} onChange={() => toggleRel('satisfies')} /> satisfies
            </label>
            <button className="btn btn-ghost" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="wide-panel-body">
          {!activeProduct && <div className="text-muted">Select a product first.</div>}
          {loading && <div className="panel-loading"><div className="spinner" /></div>}
          {!loading && matrix && (
            <div className="trace-wrap">
              <table className="trace-table">
                <thead>
                  <tr>
                    <th className="trace-th trace-th--id">ID</th>
                    <th className="trace-th trace-th--title">Title</th>
                    {matrix.teams.map(t => (
                      <th key={t} className="trace-th trace-th--team">{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.requirements.map(r => (
                    <tr key={r.uid} className="trace-row">
                      <td className="trace-td trace-td--id mono">{r.id}</td>
                      <td className="trace-td trace-td--title">{r.title}</td>
                      {matrix.teams.map(t => (
                        <td key={t} className="trace-td trace-td--cell">
                          {r.teams[t] ? <span className="trace-check">✓</span> : ''}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!loading && matrix && matrix.teams.length === 0 && (
            <div className="text-muted">
              No teams allocated. Use Allocated To on requirements to populate this matrix.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
