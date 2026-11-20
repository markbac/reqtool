/**
 * ResolveDialog.jsx -- Accept a decision: the decision text (required), rationale, the chosen option and an
 * optional linked decision or ADR. Requirements that refer to it are asked to check their wording (#371).
 */

import { useState, useEffect } from 'react';
import { api } from '../api';
import './CommitModal.css';

export default function ResolveDialog({ tbd, onResolved, onClose }) {
  const [decision, setDecision] = useState('');
  const [rationale, setRationale] = useState('');
  const [chosen, setChosen] = useState('');
  const [linked, setLinked] = useState('');
  const [decisions, setDecisions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.decisions.list().then(list => setDecisions(list.filter(d => d.uid !== tbd.uid))).catch(() => {});
  }, [tbd.uid]);

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
      if (chosen) body.chosen_option = chosen;
      if (linked) body.linked_decision = linked;
      await onResolved(body);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const affected = tbd.affected_requirements ?? [];
  const options = tbd.content?.options ?? [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-label={`Accept ${tbd.id}`} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Accept {tbd.id}</span>
          <button className="modal-close btn-ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">
          {options.length > 0 && (
            <div className="field-group">
              <label className="field-label" htmlFor="resolve-option">Chosen option <span className="field-label-optional">(optional)</span></label>
              <select id="resolve-option" value={chosen} onChange={e => setChosen(e.target.value)}>
                <option value="">None</option>
                {options.map((o, i) => <option key={o.id || i} value={o.id || o.title}>{o.title || o.id}</option>)}
              </select>
            </div>
          )}
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
            <label className="field-label" htmlFor="resolve-link">Linked decision or ADR <span className="field-label-optional">(optional)</span></label>
            <select id="resolve-link" value={linked} onChange={e => setLinked(e.target.value)}>
              <option value="">None</option>
              {decisions.map(d => <option key={d.uid} value={d.uid}>{d.id} -- {d.title}</option>)}
            </select>
          </div>
          <div className="field-group">
            <label className="field-label">Requirements waiting on this ({affected.length})</label>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {affected.length
                ? 'Each of them will be asked to check that its wording still fits. Their text is not changed.'
                : 'No requirements link to this decision.'}
            </div>
          </div>
          {error && <div className="form-error" role="alert" style={{ color: 'var(--accent-red)' }}>{error}</div>}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={!decision.trim() || busy}>
            {busy ? <span className="spinner" /> : 'Accept decision'}
          </button>
        </div>
      </div>
    </div>
  );
}
