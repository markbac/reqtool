/**
 * CommitModal.jsx -- Save and Commit confirmation dialog.
 * Prompts for message, version increment, and optional change ref.
 */

import { useState } from 'react';
import './CommitModal.css';

export default function CommitModal({ onCommit, onClose, changes }) {
  const [message, setMessage] = useState('');
  const [increment, setIncrement] = useState('patch');
  const [changeRef, setChangeRef] = useState('');
  const [busy, setBusy] = useState(false);

  const handleSubmit = async () => {
    if (!message.trim()) return;
    setBusy(true);
    await onCommit(message.trim(), increment, changeRef.trim() || null);
    setBusy(false);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Save &amp; Commit</span>
          <button className="modal-close btn-ghost" onClick={onClose}>✕</button>
        </div>

        {changes && (
          <div className="modal-changes">{changes}</div>
        )}

        <div className="modal-body">
          <div className="field-group">
            <label className="field-label">Commit Message</label>
            <input
              value={message}
              onChange={e => setMessage(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              placeholder="Brief description of changes"
              autoFocus
            />
          </div>

          <div className="field-group">
            <label className="field-label">Version Increment</label>
            <div className="increment-group">
              {['patch', 'minor', 'major'].map(v => (
                <label key={v} className={`increment-option ${increment === v ? 'active' : ''}`}>
                  <input
                    type="radio"
                    name="increment"
                    value={v}
                    checked={increment === v}
                    onChange={() => setIncrement(v)}
                  />
                  <span className="increment-label">{v.toUpperCase()}</span>
                  <span className="increment-desc">
                    {v === 'patch' && 'Editorial / metadata'}
                    {v === 'minor' && 'New AC / rationale change'}
                    {v === 'major' && 'Shall statement changed'}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="field-group">
            <label className="field-label">Change Reference <span className="field-label-optional">(optional)</span></label>
            <input
              value={changeRef}
              onChange={e => setChangeRef(e.target.value)}
              placeholder="CR-0042, ECR-123, ..."
            />
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={!message.trim() || busy}>
            {busy ? <span className="spinner" /> : 'Commit'}
          </button>
        </div>
      </div>
    </div>
  );
}
