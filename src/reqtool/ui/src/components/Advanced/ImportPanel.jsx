import { useState } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';
import { Panel } from './Panel';

export function ImportPanel({ onClose, onDone }) {
  const { toast } = useApp();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    const reader = new FileReader();
    reader.onload = (ev) => {
      setPreview(ev.target.result?.slice(0, 1000) + (ev.target.result?.length > 1000 ? '...' : ''));
    };
    reader.readAsText(f);
  };

  const handleImport = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const text = await file.text();
      const res = await api.importCsv(text);
      setResult(res);
      toast(`Imported ${res.imported} requirements`, 'success');
      if (res.imported > 0) onDone?.();
    } catch (err) { toast(err.message, 'error'); }
    finally { setBusy(false); }
  };

  return (
    <Panel title="Import from CSV" onClose={onClose} width={540}>
      <div className="import-hint">
        Imports requirements from a CSV file. Column mapping is flexible:
        <code> id, title, status, priority, req_type, domain, owner, discipline,
        parentId, content.description, content.rationale, tags (semicolon-separated),
        allocated_to (semicolon-separated), verification_method, safety_related</code>.
        Only <strong>title</strong> is required.
      </div>

      <div className="field-group">
        <label className="field-label">CSV file</label>
        <input type="file" accept=".csv,text/csv" onChange={handleFile}
          style={{ padding: 4, cursor: 'pointer' }} />
      </div>

      {preview && (
        <div className="import-preview">
          <div className="import-preview-label">Preview (first 1000 chars)</div>
          <pre className="import-preview-text">{preview}</pre>
        </div>
      )}

      {result && (
        <div className="import-result">
          <div className="import-result-ok">✓ Imported {result.imported} requirements</div>
          {result.errors?.length > 0 && (
            <div className="import-result-errors">
              {result.errors.map((e, i) => (
                <div key={i} className="import-error-row">Row {e.row}: {e.error}</div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-primary" onClick={handleImport} disabled={!file || busy}>
          {busy ? <span className="spinner" /> : 'Import'}
        </button>
        <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
      </div>
    </Panel>
  );
}
