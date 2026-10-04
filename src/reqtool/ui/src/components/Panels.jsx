/**
 * Panels.jsx -- Validation and Export overlay panels.
 */

import { useState, useEffect } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import './Panels.css';

// ---------------------------------------------------------------------------
// Validation panel
// ---------------------------------------------------------------------------
export function ValidationPanel({ onClose }) {
  const { dispatch } = useApp();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.validate.all()
      .then(setResult)
      .catch(err => setResult({ errors: [{ message: err.message }], warnings: [] }))
      .finally(() => setLoading(false));
  }, []);

  const navigate = (uid) => {
    if (!uid) return;
    dispatch({ type: 'SELECT', uid, artefactType: 'requirement' });
    onClose();
  };

  const ValidationItem = ({ item, kind }) => (
    <div
      className={`validation-item ${kind} ${item.uid ? 'validation-item--clickable' : ''}`}
      onClick={() => item.uid && navigate(item.uid)}
      title={item.uid ? 'Click to open this requirement' : undefined}
    >
      <span className="validation-code mono">{item.code ?? kind}</span>
      <div style={{ flex: 1 }}>
        <div className="validation-msg">{item.message}</div>
        {item.field && <div className="validation-field mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>field: {item.field}</div>}
      </div>
      {item.uid && <span className="validation-nav-hint">→</span>}
    </div>
  );

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
                {result.errors.map((e, i) => <ValidationItem key={i} item={e} kind="error" />)}
              </div>
            )}

            {result.warnings?.length > 0 && (
              <div className="validation-group">
                <div className="validation-group-header warning">
                  Warnings ({result.warnings.length})
                </div>
                {result.warnings.map((w, i) => <ValidationItem key={i} item={w} kind="warning" />)}
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
  // Audit package options (ENH-07)
  const [auditScope, setAuditScope] = useState('repository');
  const [auditModule, setAuditModule] = useState('');
  const [auditSelection, setAuditSelection] = useState('');
  const [auditContent, setAuditContent] = useState(['signatures', 'requirements']);
  const toggleContent = (c) => setAuditContent(l => l.includes(c) ? l.filter(x => x !== c) : [...l, c]);

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
      } else if (format === 'reqif') {
        blob = await api.exports.reqif(body);
        filename = 'requirements.reqif';
      } else if (format === 'pdf') {
        blob = await api.exports.pdf(body);
        filename = 'specification.pdf';
      } else if (format === 'audit_package') {
        const params = { scope: auditScope, include: auditContent.join(',') };
        if (auditScope === 'product') { if (!product) { setError('Choose a product to export'); setBusy(false); return; } params.product = product; }
        if (auditScope === 'module') { if (!auditModule.trim()) { setError('Enter a module id'); setBusy(false); return; } params.module = auditModule.trim(); }
        if (auditScope === 'selection') { if (!auditSelection.trim()) { setError('Enter at least one requirement id'); setBusy(false); return; } params.uids = auditSelection.split(',').map(s => s.trim()).filter(Boolean).join(','); }
        if (!auditContent.length) { setError('Choose at least one thing to include'); setBusy(false); return; }
        const url = api.exports.auditPackage(params);
        window.open(url, '_blank');
        setBusy(false);
        return;
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
      <div className="side-panel" onClick={e => e.stopPropagation()} style={{ width: 420 }}>
        <div className="side-panel-header">
          <span className="side-panel-title">Export</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="panel-body">
          <div className="field-group">
            <label className="field-label">Format</label>
            <div className="export-format-group" style={{ flexWrap: 'wrap' }}>
              {[
                { id: 'csv', label: 'CSV' },
                { id: 'markdown', label: 'MARKDOWN' },
                { id: 'jsx', label: 'JSX' },
                { id: 'reqif', label: 'ReqIF 1.2' },
                { id: 'pdf', label: 'PDF' },
                { id: 'audit_package', label: 'Audit Package (Part 11)' }
              ].map(f => (
                <label key={f.id} className={`export-format-option ${format === f.id ? 'active' : ''}`}>
                  <input type="radio" name="format" value={f.id} checked={format === f.id} onChange={() => setFormat(f.id)} />
                  <span className="mono" style={{ fontSize: 11 }}>{f.label}</span>
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

          {format === 'audit_package' && (
            <div className="field-group" style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-secondary)', padding: 8, borderRadius: 4 }}>
              Generates a 21 CFR Part 11 / ISO 26262 audit zip package for the scope and contents you choose.
              <div style={{ marginTop: 6 }}>
                <label>Scope{' '}
                  <select aria-label="Audit scope" value={auditScope} onChange={e => setAuditScope(e.target.value)}>
                    {['repository', 'product', 'module', 'selection'].map(s => <option key={s} value={s}>{s}</option>)}
                  </select></label>
                {auditScope === 'module' && <input aria-label="Module id" placeholder="module id" value={auditModule} onChange={e => setAuditModule(e.target.value)} />}
                {auditScope === 'selection' && <input aria-label="Requirement ids" placeholder="FR-001, FR-002" value={auditSelection} onChange={e => setAuditSelection(e.target.value)} />}
              </div>
              <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                {['signatures', 'requirements', 'traceability', 'history', 'validation', 'decisions'].map(c => (
                  <label key={c}><input type="checkbox" checked={auditContent.includes(c)} onChange={() => toggleContent(c)} /> {c}</label>))}
              </div>
            </div>
          )}

          {error && <div className="panel-error">{error}</div>}

          <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleExport} disabled={busy}>
            {busy ? <span className="spinner" /> : `↓ Export ${format.toUpperCase()}`}
          </button>
        </div>
      </div>
    </div>
  );
}
