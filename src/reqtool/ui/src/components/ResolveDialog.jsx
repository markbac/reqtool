/**
 * ResolveDialog.jsx -- Resolve a TBD with a recorded decision, rationale and optional linked decision.
 */

import { useState, useEffect } from 'react';
import { api } from '../api';
import './CommitModal.css';

export default function ResolveDialog({ tbd, onResolved, onClose }) {
  const [decision, setDecision] = useState('');
  const [rationale, setRationale] = useState('');
  const [linked, setLinked] = useState('');
  const [decisions, setDecisions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.decisions.list().then(list => setDecisions(list.filter(d => d.type === 'decision'))).catch(() => {});
  }, []);

  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [busy, onClose]);

  const submit = async () => {
    if (!decision.trim()) return;
    setBusy(true); setError(null);
    try {
      const body = { decision: decision.trim() };
      if (rationale.trim()) body.rationale = rationale.trim();
      if (linked) body.linked_decision = linked;
      await onResolved(body);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const affected = tbd.affected_requirements ?? [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-label={`Resolve ${tbd.id}`} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Resolve {tbd.id}</span>
          <button className="modal-close btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <div className="field-group">
            <label className="field-label" htmlFor="resolve-decision">Decision</label>
            <textarea id="resolve-decision" rows={3} autoFocus value={decision}
              onChange={e => setDecision(e.target.value)} placeholder="What was decided?" />
          </div>
          <div className="field-group">
            <label className="field-label" htmlFor="resolve-rationale">Rationale <span className="field-label-optional">(optional)</span></label>
            <textarea id="resolve-rationale" rows={2} value={rationale} onChange={e => setRationale(e.target.value)} />
          </div>
          <div className="field-group">
            <label className="field-label" htmlFor="resolve-link">Linked decision / ADR <span className="field-label-optional">(optional)</span></label>
            <select id="resolve-link" value={linked} onChange={e => setLinked(e.target.value)}>
              <option value="">None</option>
              {decisions.map(d => <option key={d.uid} value={d.uid}>{d.id} -- {d.title}</option>)}
            </select>
          </div>
          <div className="field-group">
            <label className="field-label">Affected requirements ({affected.length})</label>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {affected.length ? 'These items reference this TBD and may need review once it is resolved.' : 'No requirements reference this TBD.'}
            </div>
          </div>
          {error && <div className="form-error" role="alert" style={{ color: 'var(--accent-red)' }}>{error}</div>}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={!decision.trim() || busy}>
            {busy ? <span className="spinner" /> : 'Resolve'}
          </button>
        </div>
      </div>
    </div>
  );
}
