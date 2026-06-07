/**
 * Panels.jsx -- Validation and Export overlay panels.
 */

import { useState, useEffect } from 'react';
import { api } from '../api';
import './Panels.css';

// ---------------------------------------------------------------------------
// Validation panel
// ---------------------------------------------------------------------------
export function ValidationPanel({ onClose }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.validate.all()
      .then(setResult)
      .catch(err => setResult({ errors: [{ message: err.message }], warnings: [] }))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">Validation</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        {loading && <div className="panel-loading"><div className="spinner" /></div>}

        {result && (
          <div className="panel-body">
            {result.errors?.length === 0 && result.warnings?.length === 0 && (
              <div className="validation-pass">✓ All checks passed</div>
            )}

            {result.errors?.length > 0 && (
              <div className="validation-group">
                <div className="validation-group-header error">
                  Errors ({result.errors.length})
                </div>
                {result.errors.map((e, i) => (
                  <div key={i} className="validation-item error">
                    <span className="validation-code mono">{e.code ?? 'error'}</span>
                    <div>
                      <div className="validation-msg">{e.message}</div>
                      {e.uid && <div className="validation-uid mono">{e.uid.slice(0, 8)}...</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {result.warnings?.length > 0 && (
              <div className="validation-group">
                <div className="validation-group-header warning">
                  Warnings ({result.warnings.length})
                </div>
                {result.warnings.map((w, i) => (
                  <div key={i} className="validation-item warning">
                    <span className="validation-code mono">{w.code ?? 'warn'}</span>
                    <div>
                      <div className="validation-msg">{w.message}</div>
                      {w.uid && <div className="validation-uid mono">{w.uid.slice(0, 8)}...</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export panel
// ---------------------------------------------------------------------------
const DEFAULT_CSV_FIELDS = [
  'id', 'title', 'status', 'priority', 'req_type', 'domain',
  'owner', 'verification_method', 'verification.status', 'approval.status', 'parentId',
];

export function ExportPanel({ onClose }) {
  const [format, setFormat] = useState('csv');
  const [product, setProduct] = useState('');
  const [splitBy, setSplitBy] = useState('domain');
  const [csvFields, setCsvFields] = useState(DEFAULT_CSV_FIELDS.join('\n'));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const handleExport = async () => {
    setBusy(true); setError(null);
    try {
      const body = { product: product || undefined };
      let blob, filename;

      if (format === 'csv') {
        const fields = csvFields.split('\n').map(s => s.trim()).filter(Boolean);
        blob = await api.exports.csv({ ...body, fields });
        filename = 'requirements.csv';
      } else if (format === 'markdown') {
        blob = await api.exports.markdown({ ...body, split_by: splitBy });
        filename = 'requirements.zip';
      } else {
        blob = await api.exports.jsx(body);
        filename = 'requirements.jsx';
      }

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" onClick={e => e.stopPropagation()} style={{ width: 400 }}>
        <div className="side-panel-header">
          <span className="side-panel-title">Export</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="panel-body">
          <div className="field-group">
            <label className="field-label">Format</label>
            <div className="export-format-group">
              {['csv', 'markdown', 'jsx'].map(f => (
                <label key={f} className={`export-format-option ${format === f ? 'active' : ''}`}>
                  <input type="radio" name="format" value={f} checked={format === f} onChange={() => setFormat(f)} />
                  <span className="mono" style={{ fontSize: 12 }}>{f.toUpperCase()}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="field-group">
            <label className="field-label">Product <span style={{ color: 'var(--text-muted)', textTransform: 'none', fontSize: 11 }}>(optional)</span></label>
            <input value={product} onChange={e => setProduct(e.target.value)} placeholder="All products" />
          </div>

          {format === 'markdown' && (
            <div className="field-group">
              <label className="field-label">Split By</label>
              <select value={splitBy} onChange={e => setSplitBy(e.target.value)}>
                <option value="domain">domain</option>
                <option value="product">product</option>
                <option value="none">none (single file)</option>
              </select>
            </div>
          )}

          {format === 'csv' && (
            <div className="field-group">
              <label className="field-label">Fields <span style={{ color: 'var(--text-muted)', textTransform: 'none', fontSize: 11 }}>(one per line)</span></label>
              <textarea
                value={csvFields}
                onChange={e => setCsvFields(e.target.value)}
                rows={8}
                style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}
              />
            </div>
          )}

          {error && <div className="panel-error">{error}</div>}

          <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleExport} disabled={busy}>
            {busy ? <span className="spinner" /> : `↓ Download ${format.toUpperCase()}`}
          </button>
        </div>
      </div>
    </div>
  );
}
