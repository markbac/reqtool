import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';
import { Panel } from './Advanced/Panel';
import { MermaidView } from './MermaidView';
import './Workflow.css';

const STATE_ID = /^[a-z][a-z0-9_]*$/;
const clone = (v) => JSON.parse(JSON.stringify(v));

const blankGuard = () => ({ requires_fields: [], requires_ac: false, requires_children_in: [], children_enforce: 'warn', message: '' });

/** The pure edits, kept apart from the screen so they can be tested on their own. */
export const edit = {
  addState(def, id) {
    const next = clone(def);
    next.states.push({ id, label: id.charAt(0).toUpperCase() + id.slice(1).replace(/_/g, ' '), colour: '#8b949e', terminal: false });
    next.transitions[id] = [];
    next.guards[id] = blankGuard();
    return next;
  },
  removeState(def, id) {
    const next = clone(def);
    next.states = next.states.filter(s => s.id !== id);
    delete next.transitions[id]; delete next.guards[id];
    for (const k of Object.keys(next.transitions)) next.transitions[k] = next.transitions[k].filter(t => t !== id);
    for (const g of Object.values(next.guards)) g.requires_children_in = (g.requires_children_in || []).filter(t => t !== id);
    if (next.initial === id) next.initial = next.states[0]?.id || '';
    return next;
  },
  setState(def, id, patch) {
    const next = clone(def);
    next.states = next.states.map(s => (s.id === id ? { ...s, ...patch } : s));
    return next;
  },
  toggleTransition(def, from, to) {
    const next = clone(def);
    const list = next.transitions[from] || [];
    next.transitions[from] = list.includes(to) ? list.filter(t => t !== to) : [...list, to];
    return next;
  },
  setGuard(def, id, patch) {
    const next = clone(def);
    next.guards[id] = { ...blankGuard(), ...(next.guards[id] || {}), ...patch };
    return next;
  },
};

function StateRows({ def, setDef, locked }) {
  const [newId, setNewId] = useState('');
  const taken = def.states.some(s => s.id === newId);
  const valid = STATE_ID.test(newId) && !taken;
  return (
    <section className="we-section">
      <div className="metrics-section-title">States</div>
      <table className="we-table">
        <thead><tr><th>Start</th><th>Id</th><th>Label</th><th>Colour</th><th>End</th><th /></tr></thead>
        <tbody>
          {def.states.map(s => (
            <tr key={s.id}>
              <td><input type="radio" name="initial" aria-label={`${s.id} is the start state`} checked={def.initial === s.id}
                disabled={locked} onChange={() => setDef({ ...def, initial: s.id })} /></td>
              <td className="mono">{s.id}</td>
              <td><input aria-label={`Label of ${s.id}`} value={s.label} disabled={locked} onChange={e => setDef(edit.setState(def, s.id, { label: e.target.value }))} /></td>
              <td><input type="color" aria-label={`Colour of ${s.id}`} value={s.colour} disabled={locked} onChange={e => setDef(edit.setState(def, s.id, { colour: e.target.value }))} /></td>
              <td><input type="checkbox" aria-label={`${s.id} is an end state`} checked={s.terminal} disabled={locked} onChange={e => setDef(edit.setState(def, s.id, { terminal: e.target.checked }))} /></td>
              <td><button className="btn btn-ghost" disabled={locked || def.states.length <= 1} aria-label={`Remove ${s.id}`} onClick={() => setDef(edit.removeState(def, s.id))}>✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!locked && (
        <div className="we-add">
          <input placeholder="new_state_id" aria-label="New state id" value={newId} onChange={e => setNewId(e.target.value.trim())} />
          <button className="btn btn-secondary" disabled={!valid} onClick={() => { setDef(edit.addState(def, newId)); setNewId(''); }}>Add state</button>
          {newId && !valid && <span className="text-muted" style={{ fontSize: 11 }}>{taken ? 'Already used' : 'Lower case letters, digits and underscores, starting with a letter'}</span>}
        </div>
      )}
    </section>
  );
}

function TransitionMatrix({ def, setDef, locked }) {
  return (
    <section className="we-section">
      <div className="metrics-section-title">Moves allowed (row: from, column: to)</div>
      <div className="we-scroll">
        <table className="we-table we-matrix">
          <thead><tr><th />{def.states.map(s => <th key={s.id} title={s.label}>{s.id}</th>)}</tr></thead>
          <tbody>
            {def.states.map(from => (
              <tr key={from.id}>
                <th className="mono">{from.id}</th>
                {def.states.map(to => (
                  <td key={to.id}>
                    {from.id === to.id ? '' : (
                      <input type="checkbox" aria-label={`${from.id} to ${to.id}`} disabled={locked}
                        checked={(def.transitions[from.id] || []).includes(to.id)}
                        onChange={() => setDef(edit.toggleTransition(def, from.id, to.id))} />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function GuardEditor({ def, setDef, knownFields, locked }) {
  const [open, setOpen] = useState(null);
  const [custom, setCustom] = useState('');
  const paths = Object.keys(knownFields || {});
  return (
    <section className="we-section">
      <div className="metrics-section-title">What a move into each state needs</div>
      {def.states.map(s => {
        const g = { ...blankGuard(), ...(def.guards[s.id] || {}) };
        const summary = [g.requires_fields.length && `${g.requires_fields.length} field(s)`, g.requires_ac && 'acceptance criteria',
          g.requires_children_in.length && 'children ' + g.requires_children_in.join('/')].filter(Boolean).join(', ') || 'nothing';
        const set = (patch) => setDef(edit.setGuard(def, s.id, patch));
        const fields = [...paths, ...g.requires_fields.filter(f => !paths.includes(f))];
        return (
          <div key={s.id} className="we-guard">
            <button className="btn btn-ghost we-guard-head" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>
              {open === s.id ? '▾' : '▸'} <span className="mono">{s.id}</span> <span className="text-muted">needs {summary}</span>
            </button>
            {open === s.id && (
              <fieldset className="we-guard-body" disabled={locked}>
                <div className="we-label">Fields that must be filled in</div>
                <div className="we-chips">
                  {fields.map(f => (
                    <label key={f} className="we-chip">
                      <input type="checkbox" checked={g.requires_fields.includes(f)}
                        onChange={e => set({ requires_fields: e.target.checked ? [...g.requires_fields, f] : g.requires_fields.filter(x => x !== f) })} />
                      {knownFields[f] || f}
                    </label>
                  ))}
                </div>
                <div className="we-add">
                  <input placeholder="another field, e.g. content.rationale" aria-label={`Other field for ${s.id}`} value={custom} onChange={e => setCustom(e.target.value.trim())} />
                  <button className="btn btn-secondary" disabled={!custom || g.requires_fields.includes(custom)}
                    onClick={() => { set({ requires_fields: [...g.requires_fields, custom] }); setCustom(''); }}>Add field</button>
                </div>
                <label className="we-chip"><input type="checkbox" checked={g.requires_ac} onChange={e => set({ requires_ac: e.target.checked })} /> Needs at least one acceptance criterion</label>
                <div className="we-label">Children must already be in</div>
                <div className="we-chips">
                  {def.states.map(c => (
                    <label key={c.id} className="we-chip">
                      <input type="checkbox" checked={g.requires_children_in.includes(c.id)}
                        onChange={e => set({ requires_children_in: e.target.checked ? [...g.requires_children_in, c.id] : g.requires_children_in.filter(x => x !== c.id) })} />
                      {c.id}
                    </label>
                  ))}
                </div>
                <label className="we-label">If children are not
                  <select value={g.children_enforce} onChange={e => set({ children_enforce: e.target.value })} style={{ marginLeft: 6 }}>
                    <option value="off">do nothing</option><option value="warn">warn</option><option value="error">block the move</option>
                  </select>
                </label>
                <label className="we-label">Message shown when the move is refused
                  <textarea rows={2} value={g.message} onChange={e => set({ message: e.target.value })} />
                </label>
              </fieldset>
            )}
          </div>
        );
      })}
    </section>
  );
}

/** Administrators: change the workflows stored in the repository's hierarchy.yaml, with a live diagram. */
export function WorkflowEditor({ onClose }) {
  const { dispatch, toast } = useApp();
  const can = useCan();
  const locked = !can('manage_workflow');
  const [data, setData] = useState(null);
  const [id, setId] = useState(null);
  const [def, setDef] = useState(null);
  const [saved, setSaved] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fallback, setFallback] = useState(null);

  const load = useCallback(async (select) => {
    const next = await api.workflows.list();
    setData(next);
    const pick = next.workflows.find(w => w.id === (select || id)) || next.workflows[0];
    if (pick) { setId(pick.id); setDef(clone(pick.definition)); setSaved(clone(pick.definition)); }
    return next;
  }, [id]);

  useEffect(() => { load().catch(e => toast(e.message, 'error')); }, []);

  // Draw and check the definition as it is being edited (the server makes the diagram).
  useEffect(() => {
    if (!def || !id) return undefined;
    const timer = setTimeout(() => {
      api.workflows.preview(def, id).then(setPreview).catch(e => setPreview({ errors: [e.message], warnings: [], mermaid: '' }));
    }, 250);
    return () => clearTimeout(timer);
  }, [def, id]);

  const dirty = useMemo(() => JSON.stringify(def) !== JSON.stringify(saved), [def, saved]);
  const errors = preview?.errors || [];

  const refreshApp = async () => {
    // The tree, the status buttons and the Kanban board read the hierarchy once; hand them the new one.
    const hierarchy = await api.hierarchy.get().catch(() => null);
    if (hierarchy) dispatch({ type: 'SET_HIERARCHY', payload: hierarchy });
  };

  const run = async (fn, done) => {
    setBusy(true);
    try { await fn(); await refreshApp(); if (done) toast(done, 'success'); }
    catch (err) { toast(err.message, 'error', 6000); }
    finally { setBusy(false); }
  };

  const choose = (next) => {
    if (dirty && !confirm('Discard the changes to this workflow?')) return;
    const w = data.workflows.find(x => x.id === next);
    setId(next); setDef(clone(w.definition)); setSaved(clone(w.definition)); setPreview(null);
  };

  const create = (copyFrom) => {
    const name = prompt(copyFrom ? `Id for the copy of ${copyFrom} (lower case letters, digits, underscores)` : 'Id for the new workflow (lower case letters, digits, underscores)');
    if (!name) return;
    run(async () => { await api.workflows.create({ id: name.trim(), copy_from: copyFrom || undefined }); await load(name.trim()); }, 'Workflow created');
  };

  const remove = () => {
    if (!confirm(`Delete the workflow "${id}"?`)) return;
    run(async () => { await api.workflows.remove(id); setId(null); await load(); }, 'Workflow deleted');
  };

  const save = () => run(async () => { await api.workflows.save(id, def); await load(id); }, 'Workflow saved to hierarchy.yaml');

  const assign = (typeId, workflow) => run(async () => { await api.workflows.assign(typeId, workflow); await load(id); }, `${typeId} now uses ${workflow}`);

  const showFallback = () => api.workflow.mermaid().then(r => setFallback(r.mermaid)).catch(e => toast(e.message, 'error'));

  if (!data || !def) return <Panel title="Workflows" onClose={onClose} width={860}><div className="panel-loading"><div className="spinner" /></div></Panel>;

  const usedBy = Object.entries(data.types).filter(([, w]) => w === id).map(([t]) => t);
  return (
    <Panel title="Workflows" onClose={onClose} width={860}>
      <div className="import-hint">
        Workflows are stored in <code>.reqtool/hierarchy.yaml</code> in this repository, so each project owns its own.
        {locked && ' You can look at them here; only an administrator can change them.'}
      </div>
      <div className="we-bar">
        <select aria-label="Workflow" value={id} onChange={e => choose(e.target.value)}>
          {data.workflows.map(w => <option key={w.id} value={w.id}>{w.id}</option>)}
        </select>
        {!locked && <>
          <button className="btn btn-secondary" disabled={busy} onClick={() => create(null)}>New</button>
          <button className="btn btn-secondary" disabled={busy} onClick={() => create(id)}>Copy</button>
          <button className="btn btn-danger" disabled={busy || usedBy.length > 0} title={usedBy.length ? 'In use: give those item types another workflow first' : 'Delete this workflow'} onClick={remove}>Delete</button>
        </>}
      </div>
      <div className="text-muted" style={{ fontSize: 11 }}>Used by: {usedBy.join(', ') || 'no item type'}</div>

      <section className="we-section">
        <div className="metrics-section-title">Diagram</div>
        <MermaidView source={preview?.mermaid || data.workflows.find(w => w.id === id)?.mermaid} />
        {errors.length > 0 && <ul className="we-errors" role="alert">{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
        {(preview?.warnings || []).length > 0 && <ul className="we-warnings">{preview.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
      </section>

      <StateRows def={def} setDef={setDef} locked={locked} />
      <TransitionMatrix def={def} setDef={setDef} locked={locked} />
      <GuardEditor def={def} setDef={setDef} knownFields={data.known_fields} locked={locked} />

      {!locked && (
        <div className="we-actions">
          <button className="btn btn-primary" onClick={save} disabled={!dirty || busy || errors.length > 0}>{busy ? <span className="spinner" /> : 'Save'}</button>
          <button className="btn btn-secondary" onClick={() => setDef(clone(saved))} disabled={!dirty}>Revert</button>
        </div>
      )}

      <section className="we-section">
        <div className="metrics-section-title">Which workflow each item type uses</div>
        <table className="we-table">
          <tbody>
            {Object.entries(data.types).map(([t, w]) => (
              <tr key={t}>
                <td className="mono">{t}</td>
                <td>
                  <select aria-label={`Workflow for ${t}`} value={w} disabled={locked || busy} onChange={e => assign(t, e.target.value)}>
                    {data.workflows.map(x => <option key={x.id} value={x.id}>{x.id}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="we-section">
        <div className="metrics-section-title">Fallback workflow</div>
        <div className="text-muted" style={{ fontSize: 11 }}>Item types with no workflow of their own use the one in <code>.reqtool/config.yaml</code>.</div>
        {fallback ? <MermaidView source={fallback} title="Fallback workflow diagram" /> : <button className="btn btn-secondary" onClick={showFallback}>Show its diagram</button>}
      </section>
    </Panel>
  );
}
