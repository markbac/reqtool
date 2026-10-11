import { useMemo, useState } from 'react';
import { useApp, useCan } from '../AppContext';

/** Every field a person might want to change while moving an item on. `kind` picks the input. */
export const DIALOG_FIELDS = [
  { path: 'title', label: 'Title', kind: 'text' },
  { path: 'content.description', label: 'Description', kind: 'area' },
  { path: 'content.rationale', label: 'Rationale', kind: 'area' },
  { path: 'content.extended_description', label: 'Extended description', kind: 'area' },
  { path: 'priority', label: 'Priority', kind: 'enum', enum: 'priority' },
  { path: 'owner', label: 'Owner', kind: 'text' },
  { path: 'assignee', label: 'Assignee', kind: 'text' },
  { path: 'component', label: 'Component', kind: 'text' },
  { path: 'domain', label: 'Domain', kind: 'enum', enum: 'domain' },
  { path: 'iteration', label: 'Iteration', kind: 'text' },
  { path: 'estimate', label: 'Estimate', kind: 'text' },
  { path: 'verification_method', label: 'Verification method', kind: 'text' },
  { path: 'safety_classification', label: 'Safety classification', kind: 'text' },
  { path: 'source_document', label: 'Source document', kind: 'text' },
  { path: 'target_release', label: 'Target release', kind: 'text' },
  { path: 'tags', label: 'Tags (comma separated)', kind: 'list' },
];

export function getPath(obj, path) {
  return path.split('.').reduce((cur, key) => (cur == null ? undefined : cur[key]), obj);
}

export function setPath(obj, path, value) {
  const [head, ...rest] = path.split('.');
  if (!rest.length) return { ...obj, [head]: value };
  return { ...obj, [head]: setPath(obj?.[head] ?? {}, rest.join('.'), value) };
}

export function isFilled(value) {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === 'object') return Object.keys(value).length > 0;
  return value !== undefined && value !== null && String(value).trim() !== '';
}

const asText = v => (Array.isArray(v) ? v.join(', ') : v ?? '');

function FieldInput({ field, value, onChange, options, highlight }) {
  const id = `td-${field.path}`;
  const common = { id, value: asText(value), 'aria-label': field.label };
  let input;
  if (field.kind === 'area') {
    input = <textarea {...common} rows={3} onChange={e => onChange(e.target.value)} />;
  } else if (field.kind === 'enum' && options?.length) {
    input = (
      <select {...common} onChange={e => onChange(e.target.value)}>
        <option value="">--</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  } else if (field.kind === 'list') {
    input = <input {...common} onChange={e => onChange(e.target.value.split(',').map(t => t.trim()).filter(Boolean))} />;
  } else {
    input = <input {...common} onChange={e => onChange(e.target.value)} />;
  }
  return (
    <label className={`td-field ${highlight ? 'td-field--required' : ''}`} htmlFor={id}>
      <span className="td-label">{field.label}{highlight && <span className="td-req"> required</span>}</span>
      {input}
    </label>
  );
}

/**
 * The pop-up shown when a status change needs data the item does not have yet. The fields the move requires come
 * first and are highlighted; every other field can still be changed. Nothing is saved until a button is pressed.
 */
export function TransitionDialog({ option, draft, onApply, onCancel }) {
  const { state } = useApp();
  const can = useCan();
  const [working, setWorking] = useState(draft);
  const ruleInfo = option.rules || {};
  const errorChecks = (ruleInfo.checks || []).filter(c => c.mode === 'error');
  const warnChecks = (ruleInfo.checks || []).filter(c => c.mode !== 'error');
  const [force, setForce] = useState(false);
  const [reason, setReason] = useState('');
  const [accepted, setAccepted] = useState(() => (ruleInfo.suggested || []).map(s => s.uid));
  const canForce = can('override_rules');
  const ruleBlocked = errorChecks.length > 0 && !(force && reason.trim());
  const [more, setMore] = useState(false);
  const requires = option.requires || {};
  const requiredPaths = (requires.fields || []).map(f => f.path);
  const known = useMemo(() => Object.fromEntries(DIALOG_FIELDS.map(f => [f.path, f])), []);
  const required = requiredPaths.map(path => known[path] || { path, label: (requires.fields.find(f => f.path === path) || {}).label || path, kind: 'text' })
    .filter(f => f.path !== 'acceptance_criteria');
  const others = DIALOG_FIELDS.filter(f => !requiredPaths.includes(f.path));
  const criteria = working.acceptance_criteria || [];
  const [criterion, setCriterion] = useState('');

  const options = (f) => state.enums?.[f.enum] || [];
  const change = (path) => (value) => setWorking(w => setPath(w, path, value));
  const addCriterion = () => {
    const text = criterion.trim();
    if (!text) return;
    setWorking(w => ({ ...w, acceptance_criteria: [...(w.acceptance_criteria || []), { uid: `new-${Date.now()}`, id: `AC-${Date.now()}`, text, links: [] }] }));
    setCriterion('');
  };

  const missing = [
    ...required.filter(f => !isFilled(getPath(working, f.path))).map(f => f.label),
    ...(requires.acceptance_criteria && !criteria.length ? ['acceptance criteria'] : []),
  ];
  const childBlocked = (requires.open_children || []).length > 0 && requires.children_enforce === 'error';
  const blocked = childBlocked || ruleBlocked;
  const extras = () => ({
    force: errorChecks.length > 0 && force, reason: reason.trim(),
    accept: (ruleInfo.suggested || []).filter(s => accepted.includes(s.uid)),
  });

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-box td-dialog" role="dialog" aria-label={`Move to ${option.label}`}
        style={{ width: 560, maxHeight: '88vh' }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Move to {option.label}</span>
          <button className="btn btn-ghost" onClick={onCancel} aria-label="Close">✕</button>
        </div>
        <div className="modal-body" style={{ overflowY: 'auto' }}>
          {requires.message && <div className="td-message">{requires.message}</div>}
          {option.problem && <div className="td-problem" role="alert">{option.problem}</div>}
          {childBlocked && (
            <div className="td-problem" role="alert">
              Children not yet {requires.children_in.join(' or ')}: {requires.open_children.map(c => c.id || c).join(', ')}
            </div>
          )}
          {errorChecks.length > 0 && (
            <div className="td-problem" role="alert">
              <div className="td-section">Blocked by a rule</div>
              <ul className="td-rules">{errorChecks.map(c => <li key={c.rule}><strong>{c.label}</strong>: {c.message}</li>)}</ul>
              {canForce ? (
                <>
                  <label className="td-force"><input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} /> Force anyway</label>
                  {force && (
                    <textarea aria-label="Reason for forcing" rows={2} value={reason} placeholder="Reason (required, saved with the item)"
                      onChange={e => setReason(e.target.value)} />
                  )}
                </>
              ) : <div className="text-muted">Your role may not go past this rule.</div>}
            </div>
          )}
          {warnChecks.length > 0 && (
            <div className="td-message" role="status">
              <ul className="td-rules">{warnChecks.map(c => <li key={c.rule}><strong>{c.label}</strong>: {c.message}</li>)}</ul>
            </div>
          )}
          {(ruleInfo.auto || []).length > 0 && (
            <div className="td-message">Also moves automatically: {ruleInfo.auto.map(a => `${a.id} to ${a.to}`).join(', ')}</div>
          )}
          {(ruleInfo.suggested || []).map(sg => (
            <label key={sg.uid} className="td-suggest">
              <input type="checkbox" checked={accepted.includes(sg.uid)}
                onChange={() => setAccepted(a => (a.includes(sg.uid) ? a.filter(x => x !== sg.uid) : [...a, sg.uid]))} />
              <span>Also move <strong>{sg.id}</strong> to {sg.to} <span className="text-muted">({sg.label})</span></span>
            </label>
          ))}
          {(ruleInfo.blocked || []).length > 0 && (
            <div className="td-message">Not moved: {ruleInfo.blocked.map(b => `${b.id} (${b.reason})`).join('; ')}</div>
          )}
          {required.length > 0 && <div className="td-section">Needed for this move</div>}
          {required.map(f => (
            <FieldInput key={f.path} field={f} highlight value={getPath(working, f.path)}
              options={f.kind === 'enum' ? options(f) : undefined} onChange={change(f.path)} />
          ))}
          {requires.acceptance_criteria && (
            <div className="td-field td-field--required">
              <span className="td-label">Acceptance criteria<span className="td-req"> required</span></span>
              {criteria.map((ac, i) => <div key={ac.id || i} className="td-ac">{ac.id}: {ac.text}</div>)}
              <div style={{ display: 'flex', gap: 6 }}>
                <input value={criterion} placeholder="Given... When... Then..." aria-label="New acceptance criterion"
                  onChange={e => setCriterion(e.target.value)} onKeyDown={e => e.key === 'Enter' && addCriterion()} />
                <button className="btn btn-secondary" onClick={addCriterion}>Add</button>
              </div>
            </div>
          )}
          <button className="btn btn-ghost td-more" onClick={() => setMore(m => !m)} aria-expanded={more}>
            {more ? '▾ Hide other fields' : '▸ Change other fields'}
          </button>
          {more && others.map(f => (
            <FieldInput key={f.path} field={f} value={getPath(working, f.path)}
              options={f.kind === 'enum' ? options(f) : undefined} onChange={change(f.path)} />
          ))}
        </div>
        <div className="modal-footer">
          {missing.length > 0 && <span className="text-muted" style={{ marginRight: 'auto', fontSize: 11 }}>Still needed: {missing.join(', ')}</span>}
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="btn btn-secondary" disabled={missing.length > 0 || blocked}
            onClick={() => onApply(working, false, extras())}>Apply to draft</button>
          <button className="btn btn-primary" disabled={missing.length > 0 || blocked}
            onClick={() => onApply(working, true, extras())}>Apply and save</button>
        </div>
      </div>
    </div>
  );
}
