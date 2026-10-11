import { useCallback, useEffect, useState } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';

const clone = (v) => JSON.parse(JSON.stringify(v));
const OVERRIDES = ['none', 'editor', 'admin'];
const KIND_HELP = {
  up: 'Checks the item being moved against its parent or ancestors',
  down: 'Checks the item being moved against its children or descendants',
  start: 'When a child starts, start its parent',
  complete: 'When all children are finished, finish the parent',
  reopen: 'When a child is reopened or added, reopen a finished parent',
  cancel: 'When a parent is cancelled, cancel its children',
};
const asList = (text) => text.split(',').map(t => t.trim()).filter(Boolean);

/** The pure edits on a rule set, kept apart from the screen so they can be tested on their own. */
export const rulesEdit = {
  setRule(cfg, id, patch) {
    const next = clone(cfg);
    next.rules = next.rules.map(r => (r.id === id ? { ...r, ...patch } : r));
    return next;
  },
  setOverride(cfg, level) { return { ...clone(cfg), override: level }; },
  isCheck: (rule) => rule.kind === 'up' || rule.kind === 'down',
};

function RuleRow({ rule, info, locked, onChange }) {
  const check = rulesEdit.isCheck(rule);
  const modes = check ? info.modes.checks : info.modes.changes;
  const scopes = info.scopes[rule.kind] || [];
  const list = (field, label) => (
    <input aria-label={`${label} for ${rule.id}`} disabled={locked} defaultValue={(rule[field] || []).join(', ')}
      onBlur={e => onChange({ [field]: asList(e.target.value) })} placeholder="state ids or @terminal" />
  );
  return (
    <tr>
      <td title={KIND_HELP[rule.kind]}><strong>{rule.label || rule.id}</strong><div className="text-muted mono">{rule.kind}</div></td>
      <td>
        <select aria-label={`Mode for ${rule.id}`} value={rule.mode} disabled={locked} onChange={e => onChange({ mode: e.target.value })}>
          {modes.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </td>
      <td>
        <select aria-label={`Scope for ${rule.id}`} value={rule.scope} disabled={locked} onChange={e => onChange({ scope: e.target.value })}>
          {scopes.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </td>
      <td>
        <input aria-label={`Levels for ${rule.id}`} type="number" min="1" style={{ width: 52 }} disabled={locked}
          value={rule.levels ?? ''} onChange={e => onChange({ levels: e.target.value ? Number(e.target.value) : null })} />
      </td>
      <td>{rule.kind === 'down' ? list('children_in', 'Children allowed in') : list('when_in', 'When in')}</td>
      <td>{list('to', 'To')}</td>
      <td>
        <select aria-label={`Who can force ${rule.id}`} value={rule.override || ''} disabled={locked || !check}
          onChange={e => onChange({ override: e.target.value || null })}>
          <option value="">default</option>
          {OVERRIDES.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      </td>
    </tr>
  );
}

/** Parent and child rules: the rule matrix, a dry run for a sample item, and the moves that were forced. */
export function RulesPanel() {
  const { toast } = useApp();
  const can = useCan();
  const locked = !can('manage_workflow');
  const [info, setInfo] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [saved, setSaved] = useState(null);
  const [forced, setForced] = useState([]);
  const [sample, setSample] = useState({ item: '', to: '' });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const next = await api.rules.get();
    setInfo(next);
    const config = { override: next.override, rules: next.rules };
    setCfg(clone(config)); setSaved(clone(config));
    api.rules.overrides().then(r => setForced(r.overrides || [])).catch(() => setForced([]));
  }, []);

  useEffect(() => { Promise.resolve().then(load).catch(e => toast(e.message, 'error')); }, []);

  if (!info || !cfg) return null;
  const dirty = JSON.stringify(cfg) !== JSON.stringify(saved);

  const save = async () => {
    setBusy(true);
    try { await api.rules.save(cfg); await load(); toast('Parent and child rules saved to hierarchy.yaml', 'success'); }
    catch (err) { toast(err.message, 'error', 7000); }
    finally { setBusy(false); }
  };

  const dryRun = async () => {
    try { setResult(await api.rules.preview(sample.item.trim(), sample.to.trim())); }
    catch (err) { setResult({ error: err.message }); }
  };

  return (
    <section className="we-section" aria-label="Parent and child rules">
      <div className="metrics-section-title">Parent and child rules</div>
      <div className="text-muted" style={{ fontSize: 11 }}>
        Checks run when an item changes status: <code>up</code> looks at its parent or ancestors, <code>down</code> at its children or descendants.
        Roll-up rules move another item for you (<code>suggest</code> asks first, <code>auto</code> just does it). Use state ids or
        <code> @initial @started @terminal @done @cancelled</code>.
      </div>
      <label className="we-inline">Who can force a blocked move{' '}
        <select aria-label="Who can force a move" value={cfg.override} disabled={locked}
          onChange={e => setCfg(rulesEdit.setOverride(cfg, e.target.value))}>
          {OVERRIDES.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
      <table className="we-table" aria-label="Rules">
        <thead><tr><th>Rule</th><th>Mode</th><th>Scope</th><th>Levels</th><th>When / children in</th><th>To</th><th>Force</th></tr></thead>
        <tbody>
          {cfg.rules.map(rule => (
            <RuleRow key={rule.id} rule={rule} info={info} locked={locked}
              onChange={patch => setCfg(c => rulesEdit.setRule(c, rule.id, patch))} />
          ))}
        </tbody>
      </table>
      {info.problems.length > 0 && <ul className="we-errors" role="alert">{info.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>}
      {!locked && (
        <div className="we-actions">
          <button className="btn btn-primary" onClick={save} disabled={!dirty || busy}>Save rules</button>
          <button className="btn btn-secondary" onClick={() => setCfg(clone(saved))} disabled={!dirty}>Revert</button>
        </div>
      )}

      <div className="metrics-section-title" style={{ marginTop: 10 }}>Try it on an item</div>
      <div className="we-bar">
        <input aria-label="Sample item" placeholder="Item id, e.g. ST-001" value={sample.item}
          onChange={e => setSample(s => ({ ...s, item: e.target.value }))} />
        <input aria-label="Move to state" placeholder="Move to, e.g. in_progress" value={sample.to}
          onChange={e => setSample(s => ({ ...s, to: e.target.value }))} />
        <button className="btn btn-secondary" disabled={!sample.item.trim() || !sample.to.trim()} onClick={dryRun}>Dry run</button>
      </div>
      {result && (
        <ul className="we-preview" aria-label="Dry run result">
          {result.error && <li className="we-errors">{result.error}</li>}
          {(result.checks || []).map(c => <li key={c.rule}>{c.mode === 'error' ? 'Blocked' : 'Warning'}: {c.message}</li>)}
          {(result.auto || []).map(a => <li key={a.uid + a.to}>Would move {a.id} from {a.from} to {a.to} ({a.label})</li>)}
          {(result.suggested || []).map(a => <li key={a.uid + a.to}>Would suggest moving {a.id} to {a.to} ({a.label})</li>)}
          {(result.blocked || []).map(a => <li key={a.uid + a.kind}>Could not move {a.id}: {a.reason}</li>)}
          {!result.error && !(result.checks || []).length && !(result.auto || []).length && !(result.suggested || []).length
            && !(result.blocked || []).length && <li>Nothing would happen.</li>}
        </ul>
      )}

      <div className="metrics-section-title" style={{ marginTop: 10 }}>Forced moves</div>
      {forced.length === 0 ? <div className="text-muted" style={{ fontSize: 11 }}>No item is currently in a state it was forced into.</div> : (
        <table className="we-table" aria-label="Forced moves">
          <thead><tr><th>Item</th><th>Status</th><th>Rule</th><th>By</th><th>Reason</th></tr></thead>
          <tbody>
            {forced.map(f => (
              <tr key={f.uid}><td className="mono">{f.id}</td><td>{f.status}</td><td>{(f.rules || []).join(', ')}</td><td>{f.by}</td><td>{f.reason}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
