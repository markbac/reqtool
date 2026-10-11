import { useState } from 'react';

/** What a blocked move said, from the error the server sent (409 workflow_guard with `rules`). */
export function ruleBlock(err) {
  const d = err?.detail;
  if (err?.status === 409 && d?.error === 'workflow_guard' && Array.isArray(d.rules) && d.rules.length) {
    return { rules: d.rules, canForce: Boolean(d.can_force), message: d.message };
  }
  return null;
}

/** One line per roll-up the server did, declined or could not do, for a toast after a save. */
export function rollupSummary(rules) {
  if (!rules) return '';
  const parts = [];
  if (rules.applied?.length) parts.push(`${rules.applied.map(a => `${a.id} to ${a.to}`).join(', ')} moved by rule`);
  if (rules.blocked?.length) parts.push(`could not move ${rules.blocked.map(b => `${b.id} (${b.reason})`).join('; ')}`);
  return parts.join('. ');
}

/** Asks for a reason before forcing a move past rules in error mode. Nothing is sent without one. */
export function ForceDialog({ block, onForce, onCancel }) {
  const [reason, setReason] = useState('');
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-box" role="dialog" aria-label="Move blocked by a rule" style={{ width: 520 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">This move is blocked by a rule</span>
          <button className="btn btn-ghost" onClick={onCancel} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">
          <ul className="td-rules" role="alert">
            {block.rules.map(r => <li key={r.rule}><strong>{r.label}</strong>: {r.message}</li>)}
          </ul>
          {block.canForce ? (
            <label className="td-field td-field--required" htmlFor="force-reason">
              <span className="td-label">Reason for forcing it<span className="td-req"> required</span></span>
              <textarea id="force-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)}
                placeholder="Why is this an exception? It is saved with the item and in its history." />
            </label>
          ) : (
            <div className="text-muted">Your role may not go past this rule. Ask an administrator, or change the item that blocks it.</div>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          {block.canForce && (
            <button className="btn btn-danger" disabled={!reason.trim()} onClick={() => onForce(reason.trim())}>Force anyway</button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Offers the roll-up moves a rule in suggest mode proposes after a save. */
export function SuggestDialog({ suggestions, onAccept, onDismiss }) {
  const [picked, setPicked] = useState(() => suggestions.map(s => s.uid));
  const toggle = (uid) => setPicked(p => (p.includes(uid) ? p.filter(x => x !== uid) : [...p, uid]));
  return (
    <div className="modal-overlay" onClick={onDismiss}>
      <div className="modal-box" role="dialog" aria-label="Suggested follow-up moves" style={{ width: 480 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Move related items too?</span>
          <button className="btn btn-ghost" onClick={onDismiss} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">
          {suggestions.map(s => (
            <label key={s.uid} className="td-suggest">
              <input type="checkbox" checked={picked.includes(s.uid)} onChange={() => toggle(s.uid)} />
              <span><strong>{s.id}</strong> {s.from} to {s.to} <span className="text-muted">({s.label}: {s.because} moved)</span></span>
            </label>
          ))}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onDismiss}>Not now</button>
          <button className="btn btn-primary" disabled={!picked.length}
            onClick={() => onAccept(suggestions.filter(s => picked.includes(s.uid)))}>Move selected</button>
        </div>
      </div>
    </div>
  );
}
