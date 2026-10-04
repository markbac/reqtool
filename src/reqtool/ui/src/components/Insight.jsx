/**
 * Insight.jsx -- Panels for overview, roadmap, decisions, modules, change sets, inbox and saved queries
 * (ENH-03/06/08, UI-05/06/09, FEAT-01/02/08/09/10/11/12), plus the per-item section used in the editor.
 */

import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import { Panel } from './Advanced/Panel';
import ResolveDialog from './ResolveDialog';
import './Insight.css';

const readText = (file) => (file.text ? file.text() : new Promise((resolve, reject) => {
  const r = new FileReader(); r.onload = () => resolve(String(r.result)); r.onerror = () => reject(r.error); r.readAsText(file);
}));

export const pct = (n) => `${Math.round(Number(n) || 0)}%`;

export function Bar({ value, label }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className="ins-bar" role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100}
      aria-label={label || 'progress'}>
      <span style={{ width: `${v}%` }} />
    </div>
  );
}

function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const reload = useCallback(() => {
    setState(s => ({ ...s, loading: true, error: null }));
    fn().then(data => setState({ data, error: null, loading: false }),
      error => setState({ data: null, error: error.message, loading: false }));
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, [reload]);
  return { ...state, reload };
}

function Tabs({ tabs, value, onChange }) {
  return (
    <div className="ins-tabs" role="tablist">
      {tabs.map(([id, label]) => (
        <button key={id} role="tab" aria-selected={value === id} className="ins-tab" onClick={() => onChange(id)}>{label}</button>
      ))}
    </div>
  );
}

function Status({ loading, error }) {
  if (loading) return <div className="panel-loading"><div className="spinner" /></div>;
  if (error) return <div className="ins-error" role="alert">{error}</div>;
  return null;
}

const Stat = ({ label, value }) => (
  <div className="ins-stat"><div className="ins-stat-value">{value}</div><div className="ins-stat-label">{label}</div></div>
);

// ---------------------------------------------------------------------------
// Overview, release gate, trend and health (ENH-03, FEAT-01, FEAT-12, FEAT-11)
// ---------------------------------------------------------------------------
export function OverviewPanel({ onClose }) {
  const { state, dispatch } = useApp();
  const product = state.activeProduct?.id;
  const [tab, setTab] = useState('overview');
  const overview = useLoad(() => api.overview(product), [product]);
  const gate = useLoad(() => api.gate(product), [product]);
  const trend = useLoad(() => api.trend(), []);
  const doctor = useLoad(() => api.doctor(), []);
  const open = (uid) => { dispatch({ type: 'SELECT', uid, artefactType: 'requirement' }); onClose(); };
  const types = Object.keys(state.hierarchy?.types || {});
  const [pair, setPair] = useState({ source: types[0] || 'stakeholder_need', target: types[1] || 'functional' });
  const coverage = useLoad(() => api.traceability.coverage(pair.source, pair.target), [pair.source, pair.target]);
  const [ingest, setIngest] = useState(null);
  const upload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    try { setIngest(await api.testResults(await readText(file))); overview.reload(); } catch (err) { setIngest({ error: err.message }); }
  };

  return (
    <Panel title={`Overview${product ? `: ${product}` : ''}`} onClose={onClose} width={600}>
      <Tabs value={tab} onChange={setTab} tabs={[['overview', 'Overview'], ['gate', 'Release gate'], ['trend', 'Trend'], ['coverage', 'Coverage'], ['health', 'Health'], ['tests', 'Test results']]} />
      {tab === 'overview' && <>
        <Status {...overview} />
        {overview.data && <>
          <div className="ins-grid">
            <Stat label="Requirements" value={overview.data.counts.requirements} />
            <Stat label="Open TBDs" value={overview.data.counts.open_tbds} />
            <Stat label="Decisions" value={overview.data.counts.decisions} />
            <Stat label="Modules" value={overview.data.counts.modules} />
            <Stat label="Validation errors" value={overview.data.validation.errors} />
            <Stat label="Warnings" value={overview.data.validation.warnings} />
          </div>
          {[['approved', 'Approved'], ['verified', 'Verified'], ['traced', 'Traced']].map(([k, label]) => (
            <div className="ins-row" key={k}>
              <span style={{ width: 70 }}>{label}</span><div className="grow"><Bar value={overview.data.percentages[k]} label={label} /></div>
              <span>{pct(overview.data.percentages[k])}</span>
            </div>
          ))}
          <h4>By status</h4>
          {Object.entries(overview.data.by_status).map(([s, n]) => (
            <div className="ins-row" key={s}><span className="grow">{s.replace(/_/g, ' ')}</span><span>{n}</span></div>
          ))}
          <h4>Baselines</h4>
          <div className="ins-muted">{overview.data.baselines.length ? overview.data.baselines.map(b => b.replace('baseline/', '')).join(', ') : 'None yet'}</div>
        </>}
      </>}
      {tab === 'gate' && <>
        <Status {...gate} />
        {gate.data && (gate.data.ready
          ? <div className="ins-pill green" role="status">Ready: no policy findings</div>
          : <>
              <div className="ins-pill red" role="status">{gate.data.count} finding(s) block the release</div>
              {gate.data.findings.map((f, i) => (
                <div key={i} className={`ins-row ${f.uid ? 'ins-clickable' : ''}`} onClick={() => f.uid && open(f.uid)}>
                  <span className="ins-pill red">{f.code}</span><span className="mono">{f.id}</span><span className="grow">{f.message}</span>
                </div>
              ))}
            </>)}
      </>}
      {tab === 'trend' && <>
        <Status {...trend} />
        {trend.data && !trend.data.points.length && <div className="ins-muted">Create baselines to see a trend.</div>}
        {trend.data?.points.length > 0 && (
          <table style={{ width: '100%', fontSize: 12 }}>
            <thead><tr><th align="left">Baseline</th><th>Reqs</th><th>Approved</th><th>Verified</th><th>Traced</th><th>TBDs</th><th>Churn</th></tr></thead>
            <tbody>{trend.data.points.map(p => (
              <tr key={p.baseline}>
                <td className="mono">{p.baseline}</td><td align="center">{p.requirements}</td><td align="center">{pct(p.approved_pct)}</td>
                <td align="center">{pct(p.verified_pct)}</td><td align="center">{pct(p.traced_pct)}</td><td align="center">{p.open_tbds}</td>
                <td align="center">+{p.churn.added} -{p.churn.removed} ~{p.churn.changed}</td>
              </tr>))}</tbody>
          </table>
        )}
        <p><a href={api.snapshotUrl()} download>Download stakeholder snapshot (zip)</a></p>
      </>}
      {tab === 'coverage' && <>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {['source', 'target'].map(k => (
            <label key={k} style={{ fontSize: 12 }}>{k === 'source' ? 'Source type' : 'Target type'}{' '}
              <input list="ins-types" aria-label={k === 'source' ? 'Source type' : 'Target type'} value={pair[k]}
                onChange={e => setPair(p => ({ ...p, [k]: e.target.value }))} /></label>))}
          <datalist id="ins-types">{types.map(t => <option key={t} value={t} />)}</datalist>
        </div>
        <Status {...coverage} />
        {coverage.data && <>
          <div className="ins-row"><span className="grow">{coverage.data.covered_sources} of {coverage.data.total_sources} {coverage.data.source_type} items have a {coverage.data.target_type}</span>
            <div style={{ width: 80 }}><Bar value={coverage.data.coverage_pct} label="Coverage" /></div><span>{pct(coverage.data.coverage_pct)}</span></div>
          {coverage.data.matrix.map(r => (
            <div key={r.source.uid} className="ins-row ins-clickable" onClick={() => open(r.source.uid)}>
              <span className="mono">{r.source.id}</span><span className="grow" title={r.source.title}>{r.source.title}</span>
              {r.targets.length ? <span className="ins-pill green">{r.targets.map(t => t.id).join(', ')}</span> : <span className="ins-pill red">not covered</span>}
            </div>))}
        </>}
      </>}
      {tab === 'health' && <>
        <Status {...doctor} />
        {doctor.data && (doctor.data.checks.length === 0
          ? <div className="ins-pill green" role="status">No problems found</div>
          : doctor.data.checks.map((c, i) => (
              <div className="ins-row" key={i}><span className={`ins-pill ${c.level === 'error' ? 'red' : 'amber'}`}>{c.level}</span>
                <span className="grow" title={c.message}>{c.message}</span></div>)))}
      </>}
      {tab === 'tests' && <>
        <div className="ins-muted">Upload JUnit XML from CI. A test whose name or class contains a requirement id (for example FR-042) sets that requirement's verification status.</div>
        <input type="file" accept=".xml,application/xml,text/xml" aria-label="JUnit XML file" onChange={upload} />
        {ingest?.error && <div className="ins-error" role="alert">{ingest.error}</div>}
        {ingest && !ingest.error && <div role="status">
          <div>{ingest.tests} test(s): {ingest.updated.length} requirement(s) updated, {ingest.unmatched_tests.length} matched no requirement</div>
          {ingest.updated.map(u => <div key={u.uid} className="ins-row"><span className="mono">{u.id}</span><span className={`ins-pill ${u.status === 'passed' ? 'green' : 'red'}`}>{u.status}</span></div>)}
        </div>}
      </>}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Roadmap: Theme > Initiative > Epic (MOD-10, ENH-06)
// ---------------------------------------------------------------------------
const HEALTH = { green: 'green', amber: 'amber', red: 'red', grey: '' };

function RoadmapNode({ node, depth, onOpen }) {
  return (
    <>
      <div className="ins-row ins-clickable" style={{ paddingLeft: depth * 16 }} onClick={() => onOpen(node.uid)}>
        <span className="ins-pill">{node.req_type}</span>
        <span className="mono">{node.id}</span>
        <span className="grow" title={node.title}>{node.title}</span>
        {node.target_release && <span className="ins-pill">{node.target_release}</span>}
        <span className="ins-pill">{node.status}</span>
        <span style={{ width: 70 }}><Bar value={node.progress_pct} label={`${node.id} progress`} /></span>
        <span style={{ width: 34, textAlign: 'right' }}>{pct(node.progress_pct)}</span>
        <span className={`ins-pill ${HEALTH[node.health] || ''}`} title="Health: red when links are suspect, green when done">{node.health}</span>
      </div>
      {node.children.map(c => <RoadmapNode key={c.uid} node={c} depth={depth + 1} onOpen={onOpen} />)}
    </>
  );
}

export function RoadmapPanel({ onClose }) {
  const { dispatch } = useApp();
  const road = useLoad(() => api.roadmap(), []);
  const open = (uid) => { dispatch({ type: 'SELECT', uid, artefactType: 'requirement' }); onClose(); };
  return (
    <Panel title="Roadmap" onClose={onClose} width={720}>
      <Status {...road} />
      {road.data && !road.data.length && <div className="ins-muted">No themes, initiatives or epics yet.</div>}
      {road.data?.map(n => <RoadmapNode key={n.uid} node={n} depth={0} onOpen={open} />)}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Decisions, ADRs and ATAM records (UI-06)
// ---------------------------------------------------------------------------
const DECISION_STATUSES = ['proposed', 'accepted', 'rejected', 'superseded'];
const lines = (t) => (t || '').split('\n').map(s => s.trim()).filter(Boolean);

function DecisionForm({ item, onSaved, onCancel }) {
  const { toast } = useApp();
  const c = item?.content || {};
  const atam = c.atam || {};
  const [f, setF] = useState({
    title: item?.title || '', status: item?.status || 'proposed', context: c.context || '', description: c.description || '',
    rationale: c.rationale || '', chosen: c.chosen_option || '',
    options: (c.options || []).map(o => `${o.name} | + ${(o.pros || []).join('; ')} | - ${(o.cons || []).join('; ')}`).join('\n'),
    atamOn: Boolean(atam.enabled), attrs: (atam.quality_attributes || []).join(', '),
    sens: (atam.sensitivity_points || []).map(s => `${s.attribute}: ${s.description}`).join('\n'),
    trade: (atam.tradeoff_points || []).map(s => `${(s.attributes || []).join('+')}: ${s.description}`).join('\n'),
    risks: (atam.risks || []).join('\n'),
  });
  const set = (k) => (e) => setF(p => ({ ...p, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const save = async () => {
    const options = lines(f.options).map(l => {
      const [name, pros = '', cons = ''] = l.split('|').map(s => s.trim());
      const split = (s) => s.replace(/^[+-]\s*/, '').split(';').map(x => x.trim()).filter(Boolean);
      return { name, pros: split(pros), cons: split(cons) };
    });
    const pair = (l) => { const i = l.indexOf(':'); return i < 0 ? [l, ''] : [l.slice(0, i).trim(), l.slice(i + 1).trim()]; };
    const content = {
      context: f.context, description: f.description, rationale: f.rationale, chosen_option: f.chosen || null, options,
      atam: f.atamOn ? {
        enabled: true, quality_attributes: f.attrs.split(',').map(s => s.trim()).filter(Boolean),
        sensitivity_points: lines(f.sens).map(l => { const [attribute, description] = pair(l); return { attribute, description }; }),
        tradeoff_points: lines(f.trade).map(l => { const [a, description] = pair(l); return { attributes: a.split('+').map(s => s.trim()).filter(Boolean), description }; }),
        risks: lines(f.risks), non_risks: atam.non_risks || [],
      } : null,
    };
    try {
      const body = { title: f.title, status: f.status, content };
      const saved = item ? await api.decisions.update(item.uid, body) : await api.decisions.create(body);
      toast(`${saved.id} saved`, 'success');
      onSaved(saved);
    } catch (err) { toast(err.message, 'error'); }
  };

  return (
    <div className="ins-form">
      <label>Title<input aria-label="Decision title" value={f.title} onChange={set('title')} /></label>
      <label>Status<select aria-label="Decision status" value={f.status} onChange={set('status')}>
        {DECISION_STATUSES.map(s => <option key={s}>{s}</option>)}</select></label>
      <label>Context<textarea rows={2} value={f.context} onChange={set('context')} /></label>
      <label>Options (one per line: name | + pros; ... | - cons; ...)<textarea rows={3} aria-label="Options" value={f.options} onChange={set('options')} /></label>
      <label>Chosen option<input value={f.chosen} onChange={set('chosen')} /></label>
      <label>Decision<textarea rows={2} value={f.description} onChange={set('description')} /></label>
      <label>Rationale<textarea rows={2} value={f.rationale} onChange={set('rationale')} /></label>
      <label><input type="checkbox" checked={f.atamOn} onChange={set('atamOn')} /> ATAM analysis</label>
      {f.atamOn && <>
        <label>Quality attributes (comma separated)<input value={f.attrs} onChange={set('attrs')} /></label>
        <label>Sensitivity points (attribute: description)<textarea rows={2} aria-label="Sensitivity points" value={f.sens} onChange={set('sens')} /></label>
        <label>Trade-off points (a+b: description)<textarea rows={2} aria-label="Trade-off points" value={f.trade} onChange={set('trade')} /></label>
        <label>Risks (one per line)<textarea rows={2} value={f.risks} onChange={set('risks')} /></label>
      </>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-primary" onClick={save} disabled={!f.title.trim()}>Save</button>
        <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

export function DecisionsPanel({ onClose }) {
  const { toast } = useApp();
  const list = useLoad(() => api.decisions.list(), []);
  const [editing, setEditing] = useState(null);   // item, or {} for a new one
  const [resolving, setResolving] = useState(null);
  const done = () => { setEditing(null); list.reload(); };
  return (
    <Panel title="Decisions, ADRs and TBDs" onClose={onClose} width={640}>
      {resolving && <ResolveDialog tbd={resolving} onClose={() => setResolving(null)}
        onResolved={async (body) => { await api.decisions.resolve(resolving.uid, body); setResolving(null); toast('Resolved to a decision', 'success'); list.reload(); }} />}
      {editing ? <DecisionForm item={editing.uid ? editing : null} onSaved={done} onCancel={() => setEditing(null)} /> : <>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={() => setEditing({})}>+ New decision</button>
          <a className="btn btn-secondary" href={api.exports.adrUrl()} download>Export ADRs</a>
        </div>
        <Status {...list} />
        {list.data && !list.data.length && <div className="ins-muted">No decisions yet.</div>}
        {list.data?.map(d => (
          <div className="ins-row" key={d.uid}>
            <span className="ins-pill">{d.type}</span><span className="mono">{d.id}</span>
            <span className="grow" title={d.title}>{d.title}</span><span className="ins-pill">{d.status}</span>
            {d.type === 'tbd'
              ? <button className="btn btn-ghost" onClick={() => setResolving(d)}>Resolve</button>
              : <button className="btn btn-ghost" onClick={() => setEditing(d)}>Edit</button>}
          </div>
        ))}
      </>}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Modules: detail, verification, consumers, versions, pinning (UI-05, ENH-08, FEAT-08)
// ---------------------------------------------------------------------------
function ModuleDetail({ id, onChanged }) {
  const { state, toast } = useApp();
  const detail = useLoad(() => api.modules.get(id), [id]);
  const consumers = useLoad(() => api.modules.consumers(id), [id]);
  const [verify, setVerify] = useState({});
  const [preview, setPreview] = useState(null);
  const [ref, setRef] = useState('');
  const run = async (fn, ok) => {
    try { const r = await fn(); if (ok) toast(ok, 'success'); detail.reload(); consumers.reload(); onChanged?.(); return r; }
    catch (err) { toast(err.message, 'error'); }
  };
  const verifyAll = async () => {
    const out = {};
    for (const c of consumers.data || []) {
      try { out[c.product] = await api.modules.verifyFor(id, c.product); } catch (err) { out[c.product] = { error: err.message }; }
    }
    setVerify(out);
  };
  const m = detail.data?.manifest;
  const product = state.activeProduct?.id;
  return (
    <div>
      <Status {...detail} />
      {m && <>
        <h3>{m.title} <span className="mono">v{m.version}</span></h3>
        <div className="ins-muted">{m.content?.description}</div>
        <div className="ins-muted">Requirements: {detail.data.requirements.length}{m.git_remote ? ` | Remote: ${m.git_remote} @ ${m.git_ref || 'main'}` : ''}{m.pinned_commit ? ` (${m.pinned_commit.slice(0, 8)})` : ''}</div>
        <h4>Used by</h4>
        {consumers.data?.length ? consumers.data.map(c => (
          <div className="ins-row" key={c.product}><span className="grow">{c.title}</span>
            <span className="ins-pill">locked {c.locked_version || 'not yet'}</span>
            {verify[c.product] && (verify[c.product].error || verify[c.product].verified === false
              ? <span className="ins-pill red" role="alert">verification failed</span> : <span className="ins-pill green">verified</span>)}
          </div>)) : <div className="ins-muted">No product includes this module.</div>}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '8px 0' }}>
          <button className="btn btn-secondary" onClick={verifyAll} disabled={!consumers.data?.length}>Verify</button>
          {product && <button className="btn btn-secondary" onClick={() => run(() => api.modules.importInto(id, product), 'Imported and locked')}>Import into {product}</button>}
          {['patch', 'minor', 'major'].map(inc => (
            <button key={inc} className="btn btn-ghost" onClick={() => run(() => api.modules.version(id, { increment: inc }), `Version bumped (${inc})`)}>Bump {inc}</button>))}
          <button className="btn btn-ghost" onClick={() => { const n = prompt('Id for the copy'); if (n) run(() => api.modules.clone(id, n), 'Module cloned'); }}>Clone</button>
        </div>
        {m.git_remote && <>
          <h4>Remote</h4>
          <div style={{ display: 'flex', gap: 6 }}>
            <input aria-label="Ref" placeholder="tag, branch or commit" value={ref} onChange={e => setRef(e.target.value)} />
            <button className="btn btn-secondary" disabled={!ref.trim()} onClick={async () => { try { setPreview(await api.modules.updatePreview(id, ref.trim())); } catch (err) { toast(err.message, 'error'); } }}>Preview update</button>
            <button className="btn btn-secondary" disabled={!ref.trim()} onClick={() => run(() => api.modules.pin(id, ref.trim()), `Pinned to ${ref.trim()}`)}>Pin</button>
            <button className="btn btn-secondary" onClick={() => run(() => api.modules.fetchRemote(id), 'Fetched')}>Fetch</button>
          </div>
          {preview && <div role="region" aria-label="Update preview">
            {['added', 'removed', 'changed'].map(k => (
              <div key={k} className="ins-muted">{k}: {preview[k].length ? preview[k].join(', ') : 'none'}</div>))}
            <div className="ins-muted">Affects {preview.consumers.length} product(s)</div>
          </div>}
        </>}
      </>}
    </div>
  );
}

export function ModulesPanel({ onClose }) {
  const { toast } = useApp();
  const list = useLoad(() => api.modules.list(), []);
  const [sel, setSel] = useState(null);
  const create = async () => {
    const id = prompt('Module id'); if (!id) return;
    try { await api.modules.create({ id, title: id }); toast('Module created', 'success'); list.reload(); setSel(id); }
    catch (err) { toast(err.message, 'error'); }
  };
  return (
    <Panel title="Modules" onClose={onClose} width={640}>
      {sel ? <>
        <button className="btn btn-ghost" onClick={() => setSel(null)}>Back to modules</button>
        <ModuleDetail id={sel} onChanged={list.reload} />
      </> : <>
        <button className="btn btn-primary" onClick={create}>+ New module</button>
        <Status {...list} />
        {list.data?.map(m => (
          <div className="ins-row ins-clickable" key={m.id} onClick={() => setSel(m.id)}>
            <span className="mono">{m.id}</span><span className="grow">{m.title}</span><span className="ins-pill">v{m.version}</span>
          </div>))}
        {list.data && !list.data.length && <div className="ins-muted">No modules yet.</div>}
      </>}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Change sets (FEAT-02)
// ---------------------------------------------------------------------------
export function ChangeSetsPanel({ onClose }) {
  const { toast } = useApp();
  const list = useLoad(() => api.changesets.list(), []);
  const [diff, setDiff] = useState(null);
  const guard = async (fn, ok) => { try { await fn(); if (ok) toast(ok, 'success'); list.reload(); } catch (err) { toast(err.message, 'error'); } };
  const create = () => { const n = prompt('Name for the change set'); if (n) guard(() => api.changesets.create(n), 'Change set started'); };
  const merge = (name) => { const who = prompt('Reviewed by'); if (who) guard(async () => { await api.changesets.merge(name, who); setDiff(null); }, 'Merged'); };
  return (
    <Panel title="Change sets" onClose={onClose} width={640}>
      <button className="btn btn-primary" onClick={create}>+ Start change set</button>
      <Status {...list} />
      {list.data && !list.data.length && <div className="ins-muted">No change sets. Start one to group edits on a branch and review them before merging.</div>}
      {list.data?.map(c => (
        <div className="ins-row" key={c.name}>
          <span className="mono grow">{c.name}</span><span className="ins-pill">base {c.base}</span>
          {c.current && <span className="ins-pill green">current</span>}
          <button className="btn btn-ghost" onClick={async () => { try { setDiff(await api.changesets.diff(c.name)); } catch (e) { toast(e.message, 'error'); } }}>Review</button>
          {!c.current && <button className="btn btn-ghost" onClick={() => guard(() => api.changesets.switchTo(c.branch), 'Switched')}>Switch</button>}
          <button className="btn btn-ghost" onClick={() => merge(c.name)}>Merge</button>
        </div>))}
      {diff && <div role="region" aria-label="Change set diff">
        <h4>{diff.name}: {diff.summary.added} added, {diff.summary.removed} removed, {diff.summary.modified} modified</h4>
        {diff.added.map(i => <div key={i.path} className="ins-row"><span className="ins-pill green">added</span>{i.id} {i.title}</div>)}
        {diff.removed.map(i => <div key={i.path} className="ins-row"><span className="ins-pill red">removed</span>{i.id} {i.title}</div>)}
        {diff.modified.map(i => (
          <div key={i.path}><div className="ins-row"><span className="ins-pill amber">changed</span>{i.id} {i.title}</div>
            {i.fields.map(f => <div key={f.field} className="ins-muted ins-indent"><b>{f.field}</b>: {JSON.stringify(f.old)} to {JSON.stringify(f.new)}</div>)}</div>))}
      </div>}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Inbox: notifications, review requests and preferences (FEAT-04, FEAT-10)
// ---------------------------------------------------------------------------
const NOTIFY_EVENTS = ['mention', 'review_requested', 'status_changed'];

export function InboxPanel({ onClose }) {
  const { state, dispatch, toast } = useApp();
  const user = state.enums?._current_user || localStorage.getItem('reqtool:username') || 'user';
  const inbox = useLoad(() => api.notifications.list(user), [user]);
  const reviews = useLoad(() => api.reviews(user), [user]);
  const prefs = useLoad(() => api.notifications.prefs(user), [user]);
  const open = (uid) => { dispatch({ type: 'SELECT', uid, artefactType: 'requirement' }); onClose(); };
  const toggle = async (ev) => {
    const cur = prefs.data.events;
    const events = cur.includes(ev) ? cur.filter(e => e !== ev) : [...cur, ev];
    try { await api.notifications.setPrefs(user, { events, muted: prefs.data.muted }); prefs.reload(); } catch (err) { toast(err.message, 'error'); }
  };
  return (
    <Panel title={`Inbox: ${user}`} onClose={onClose} width={560}>
      <h4>Review requests</h4>
      <Status {...reviews} />
      {reviews.data && !reviews.data.length && <div className="ins-muted">Nothing waiting for your review.</div>}
      {reviews.data?.map(r => (
        <div key={r.id} className="ins-row ins-clickable" onClick={() => open(r.uid)}>
          <span className="grow">{r.uid.slice(0, 8)} requested by {r.requested_by}</span>
          <span className={`ins-pill ${r.status === 'stale' ? 'amber' : ''}`}>{r.status === 'stale' ? 'changed since requested' : r.status}</span>
        </div>))}
      <h4>Notifications</h4>
      <Status {...inbox} />
      {inbox.data && !inbox.data.length && <div className="ins-muted">No notifications.</div>}
      {inbox.data?.map(n => (
        <div key={n.id} className="ins-row ins-clickable" style={{ fontWeight: n.read ? 400 : 700 }}
          onClick={async () => { await api.notifications.read(n.id, user).catch(() => {}); open(n.uid); }}>
          <span className="grow">{n.text}</span><span className="ins-muted">{n.at?.slice(0, 10)}</span>
        </div>))}
      <h4>Preferences</h4>
      {prefs.data && <>
        {NOTIFY_EVENTS.map(ev => (
          <label key={ev} style={{ display: 'block', fontSize: 12 }}>
            <input type="checkbox" checked={prefs.data.events.includes(ev)} onChange={() => toggle(ev)} /> {ev.replace(/_/g, ' ')}
          </label>))}
        <label style={{ display: 'block', fontSize: 12 }}>
          <input type="checkbox" checked={prefs.data.muted}
            onChange={async (e) => { await api.notifications.setPrefs(user, { events: prefs.data.events, muted: e.target.checked }).catch(err => toast(err.message, 'error')); prefs.reload(); }} /> Mute all
        </label>
      </>}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Query and saved views (FEAT-09, UI-09)
// ---------------------------------------------------------------------------
export function QueryPanel({ onClose }) {
  const { dispatch, toast } = useApp();
  const [q, setQ] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const views = useLoad(() => api.filterPresets.list(), []);
  const run = async (text = q) => {
    setError(null);
    try { setResult(await api.query(text)); } catch (err) { setResult(null); setError(err.message); }
  };
  const save = async () => {
    const label = prompt('Name for this view'); if (!label) return;
    const id = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'view';
    try { await api.filterPresets.save(id, { label, query: q }); views.reload(); } catch (err) { toast(err.message, 'error'); }
  };
  return (
    <Panel title="Query and saved views" onClose={onClose} width={560}>
      <div style={{ display: 'flex', gap: 6 }}>
        <input aria-label="Query" style={{ flex: 1 }} placeholder="status:approved type:safety no:verification" value={q}
          onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && run()} />
        <button className="btn btn-primary" onClick={() => run()}>Run</button>
        <button className="btn btn-secondary" onClick={save} disabled={!q.trim()}>Save view</button>
      </div>
      <div className="ins-muted">Words search titles. field:value filters, no:field finds empty ones, has:field set ones, a leading - negates.</div>
      {error && <div className="ins-error" role="alert">{error}</div>}
      {result && <>
        <h4>{result.count} match(es)</h4>
        {result.results.map(r => (
          <div className="ins-row ins-clickable" key={r.uid}
            onClick={() => { dispatch({ type: 'SELECT', uid: r.uid, artefactType: 'requirement' }); onClose(); }}>
            <span className="mono">{r.id}</span><span className="grow">{r.title}</span><span className="ins-pill">{r.status}</span>
          </div>))}
      </>}
      <h4>Saved views</h4>
      {views.data && !views.data.length && <div className="ins-muted">None saved. Views are kept in the repository, so everyone sees them.</div>}
      {views.data?.map(v => (
        <div className="ins-row" key={v.id}>
          <button className="btn btn-ghost grow" style={{ textAlign: 'left' }} onClick={() => { setQ(v.query || ''); run(v.query || ''); }}>{v.label}</button>
          <span className="mono ins-muted">{v.query}</span>
          <button className="btn btn-ghost" aria-label={`Delete ${v.label}`} onClick={async () => { await api.filterPresets.delete(v.id).catch(e => toast(e.message, 'error')); views.reload(); }}>✕</button>
        </div>))}
    </Panel>
  );
}
