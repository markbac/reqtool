/**
 * Work.jsx -- The Work area's own views.
 *
 * IssuesPage (#379): issues are reports until triage decides what they are. Triage turns an issue into a
 * defect, feature or story (the same record, with a new type and id; the old id still opens it), or rejects it.
 * BacklogPage (#378): the theme, initiative, epic, feature, story and task hierarchy, ranked, with roll-ups.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';
import Editor from './Editor';
import { labelOf } from '../labels';
import './Work.css';

// ---------------------------------------------------------------------------
// Issues
// ---------------------------------------------------------------------------
const QUEUES = [
  ['new', 'New', ['reported']],
  ['triage', 'In triage', ['in_triage']],
  ['info', 'Needs info', ['needs_info']],
  ['rejected', 'Rejected', ['user_error', 'duplicate', 'not_reproducible', 'closed', 'wont_do']],
  ['converted', 'Converted', []],
];
const REJECT_REASONS = [['user_error', 'User error'], ['duplicate', 'Duplicate'], ['not_reproducible', 'Not reproducible'],
  ['wont_do', "Won't do"]];

const ago = (iso) => {
  if (!iso) return '';
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return days <= 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
};

export function IssuesPage() {
  const { state, dispatch, toast } = useApp();
  const can = useCan();
  const [data, setData] = useState(null);
  const [queue, setQueue] = useState('new');
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api.work.issues(state.activeProduct?.id).then(d => { setData(d); setError(null); }).catch(e => setError(e.message));
  }, [state.activeProduct?.id]);
  useEffect(() => { load(); }, [load, state._lastCommit]);

  const counts = useMemo(() => Object.fromEntries(QUEUES.map(([id, , statuses]) => [id,
    id === 'converted' ? (data?.converted || []).length : (data?.issues || []).filter(i => statuses.includes(i.status)).length])), [data]);
  // Open on the first queue with something in it.
  const first = useRef(true);
  useEffect(() => {
    if (!data || !first.current) return;
    first.current = false;
    const busy = QUEUES.find(([id]) => counts[id] > 0 && id !== 'converted');
    if (busy) setQueue(busy[0]);
  }, [data, counts]);

  const statuses = QUEUES.find(q => q[0] === queue)[2];
  const rows = queue === 'converted' ? (data?.converted || []) : (data?.issues || []).filter(i => statuses.includes(i.status));
  const selected = (data?.issues || []).find(i => i.uid === state.selectedUid);

  const report = async () => {
    try {
      const item = await api.requirements.create({ title: 'New issue', req_type: 'issue' });
      dispatch({ type: 'SELECT', uid: item.uid, artefactType: 'requirement' });
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  return (
    <div className="work-split">
      <section className="work-list" aria-label="Issue queue">
        <div className="work-queues" role="tablist" aria-label="Issue queues">
          {QUEUES.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={queue === id} className={`work-queue ${queue === id ? 'work-queue--on' : ''}`}
              onClick={() => setQueue(id)}>{label} <span className="work-queue-count">{counts[id] || 0}</span></button>
          ))}
          {can('write') && <button className="btn btn-primary work-report" onClick={report}>+ Report issue</button>}
        </div>
        {error && <div className="work-error" role="alert">{error}</div>}
        {!data && !error && <div className="work-empty"><div className="spinner" /></div>}
        {data && !rows.length && <div className="work-empty">Nothing in this queue.</div>}
        <div className="work-rows">
          {rows.map(i => (
            <button key={i.uid} className={`work-row ${state.selectedUid === i.uid ? 'work-row--on' : ''}`}
              onClick={() => dispatch({ type: 'SELECT', uid: i.uid, artefactType: 'requirement' })}>
              <span className="work-row-title"><span className="mono work-id">{i.id}</span> {i.title}</span>
              <span className="work-row-meta">
                {queue === 'converted'
                  ? <>{labelOf.type(i.req_type, state.hierarchy)} · was {i.converted_from} · {labelOf.status(i.status, i.req_type, state.hierarchy)}</>
                  : <>{i.reporter && <>Reported by {i.reporter} · </>}{ago(i.created)}{i.assignee && <> · Triage: {i.assignee}</>}
                    {i.priority && <span className={`work-pill work-pill--${i.priority}`}>{labelOf.plain(i.priority)}</span>}</>}
              </span>
            </button>
          ))}
        </div>
      </section>
      <div className="work-detail">
        {selected ? <IssueDetail issue={selected} onDone={load} /> : (state.selectedUid ? <Editor /> :
          <div className="work-empty work-empty--detail">Choose an issue to triage it.</div>)}
      </div>
    </div>
  );
}

function IssueDetail({ issue, onDone }) {
  const { state, dispatch, toast } = useApp();
  const can = useCan();
  const [full, setFull] = useState(null);
  const [mode, setMode] = useState(null);           // null | 'defect' | 'work' | 'reject' | 'info'
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [showEditor, setShowEditor] = useState(false);

  useEffect(() => {
    setMode(null); setForm({}); setShowEditor(false);
    api.requirements.get(issue.uid).then(setFull).catch(() => setFull(null));
  }, [issue.uid, issue.status]);

  const cf = full?.custom_fields || {};
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));
  const triage = async (body, message) => {
    setBusy(true);
    try {
      const out = await api.requirements.triage(issue.uid, body);
      toast(message(out), 'success');
      dispatch({ type: 'COMMITTED' });
      onDone();
      if (out?.req_type && out.req_type !== 'issue') dispatch({ type: 'NAVIGATE', area: 'work', tab: 'backlog', uid: out.uid, artefactType: 'requirement' });
    } catch (err) { toast(err.message, 'error', 6000); }
    finally { setBusy(false); }
  };

  if (showEditor) return <><button className="btn btn-ghost work-back" onClick={() => setShowEditor(false)}>← Back to triage</button><Editor /></>;

  const status = labelOf.status(issue.status, 'issue', state.hierarchy);
  const open = ['reported', 'in_triage', 'needs_info'].includes(issue.status);
  return (
    <div className="issue-detail">
      <div className="issue-head">
        <h2><span className="mono work-id">{issue.id}</span> {issue.title}</h2>
        <span className="work-pill">{status}</span>
        <button className="btn btn-ghost" onClick={() => setShowEditor(true)}>Edit issue</button>
      </div>
      {can('write') && open && (
        <div className="issue-actions" role="group" aria-label="Triage">
          {issue.status === 'reported' && <button className="btn btn-secondary" disabled={busy}
            onClick={() => triage({ outcome: 'start' }, () => 'Triage started')}>Start triage</button>}
          <button className="btn btn-secondary" disabled={busy} onClick={() => setMode('info')}>Needs info</button>
          <button className="btn btn-danger-outline" disabled={busy} onClick={() => setMode('defect')}>Make it a defect</button>
          <button className="btn btn-secondary" disabled={busy} onClick={() => setMode('work')}>Make it a feature or story</button>
          <button className="btn btn-secondary" disabled={busy} onClick={() => setMode('reject')}>Reject</button>
        </div>
      )}
      <div className="issue-body">
        <div className="issue-fields">
          <IssueField label="What was seen" value={cf.observed || full?.content?.description} />
          <IssueField label="What was expected" value={cf.expected} />
          <IssueField label="Steps to reproduce" value={Array.isArray(cf.steps) ? cf.steps : cf.steps ? [cf.steps] : null} list />
          <div className="issue-facts">
            {cf.affected_version && <span>Version <span className="mono">{cf.affected_version}</span></span>}
            {cf.environment && <span>Environment {cf.environment}</span>}
            {cf.reporter && <span>Reported by {cf.reporter}</span>}
          </div>
          <IssueField label="Triage note" value={cf.triage_note} />
        </div>
        {mode && (
          <form className={`issue-panel issue-panel--${mode}`} onSubmit={e => {
            e.preventDefault();
            if (mode === 'info') triage({ outcome: 'needs_info', note: form.note }, () => 'Asked the reporter for more');
            if (mode === 'reject') triage({ outcome: 'rejected', reason: form.reason || 'user_error', note: form.note,
              duplicate_of: form.duplicate_of }, () => 'Issue rejected');
            if (mode === 'defect' || mode === 'work') triage({ outcome: mode === 'defect' ? 'defect' : (form.kind || 'story'),
              parent: form.parent || null, link: form.link || null, note: form.note, priority: form.priority || issue.priority },
            out => `${issue.id} is now ${out.id}`);
          }}>
            <h3>{{ info: 'Needs info', reject: 'Reject the issue', defect: 'Make it a defect', work: 'Make it a feature or story' }[mode]}</h3>
            {(mode === 'defect' || mode === 'work') && (
              <p className="issue-explain">This issue becomes a {mode === 'defect' ? 'defect' : 'work item'}. Comments, attachments and
                history stay with it, and <span className="mono">{issue.id}</span> keeps working as a link.</p>
            )}
            {mode === 'work' && (
              <label>Becomes a<select value={form.kind || 'story'} onChange={set('kind')}>
                <option value="story">Story</option><option value="feature">Feature</option></select></label>
            )}
            {(mode === 'defect' || mode === 'work') && <>
              <label>{mode === 'defect' ? 'Requirement it breaks' : 'Requirement it satisfies or changes'}
                <ItemPicker value={form.link} onChange={v => setForm(f => ({ ...f, link: v }))} family="requirement" /></label>
              <label>Parent <ItemPicker value={form.parent} onChange={v => setForm(f => ({ ...f, parent: v }))} family="work" /></label>
              <label>Priority<select value={form.priority || issue.priority || 'medium'} onChange={set('priority')}>
                {['critical', 'high', 'medium', 'low'].map(p => <option key={p} value={p}>{labelOf.plain(p)}</option>)}</select></label>
            </>}
            {mode === 'reject' && <>
              <label>Reason<select value={form.reason || 'user_error'} onChange={set('reason')}>
                {REJECT_REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
              {form.reason === 'duplicate' && <label>Duplicate of<input value={form.duplicate_of || ''} onChange={set('duplicate_of')}
                placeholder="ISS-003" required /></label>}
            </>}
            <label>{mode === 'info' ? 'What do you need from the reporter?' : 'Triage note'}
              <textarea rows={3} value={form.note || ''} onChange={set('note')} required={mode !== 'defect' && mode !== 'work'} /></label>
            <div className="issue-panel-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setMode(null)}>Cancel</button>
              <button type="submit" className={`btn ${mode === 'defect' || mode === 'reject' ? 'btn-danger' : 'btn-primary'}`} disabled={busy}>
                {{ info: 'Ask for info', reject: 'Reject', defect: 'Make it a defect', work: `Make it a ${form.kind || 'story'}` }[mode]}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function IssueField({ label, value, list }) {
  if (!value || (Array.isArray(value) && !value.length)) return null;
  return (
    <div className="issue-field">
      <div className="issue-field-label">{label}</div>
      {list ? <ol>{value.map((v, i) => <li key={i}>{v}</li>)}</ol> : <div className="issue-field-value">{value}</div>}
    </div>
  );
}

/** Pick an item by id or title. ``family`` limits the choice to requirements or to work items. */
function ItemPicker({ value, onChange, family }) {
  const { state } = useApp();
  const [q, setQ] = useState('');
  const [hits, setHits] = useState([]);
  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return; }
    const t = setTimeout(() => api.search(q.trim(), 12).then(r => setHits((r || []).filter(h => h.type === 'requirement'))).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [q]);
  const wanted = hits.filter(h => !h.req_type || labelOf.family(h.req_type, state.hierarchy) === family);
  return (
    <span className="item-picker">
      {value ? <span className="item-picker-value">{value.id} {value.title}
        <button type="button" className="btn btn-ghost" aria-label="Clear" onClick={() => onChange(null)}>✕</button></span>
        : <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search by id or title" />}
      {!value && wanted.length > 0 && (
        <span className="item-picker-list" role="listbox">
          {wanted.map(h => <button type="button" role="option" key={h.uid} onClick={() => { onChange({ uid: h.uid, id: h.id, title: h.title }); setQ(''); }}>
            <span className="mono">{h.id}</span> {h.title}</button>)}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Backlog
// ---------------------------------------------------------------------------
export function BacklogPage() {
  const { state, dispatch, toast } = useApp();
  const can = useCan();
  const [tree, setTree] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState({});
  const [filters, setFilters] = useState({ type: '', status: 'open', iteration: '', assignee: '', text: '' });
  const dragged = useRef(null);

  const load = useCallback(() => {
    api.work.backlog(state.activeProduct?.id).then(d => { setTree(d.items); setError(null); }).catch(e => setError(e.message));
  }, [state.activeProduct?.id]);
  useEffect(() => { load(); }, [load, state._lastCommit]);
  useEffect(() => {
    // Open the top two levels the first time.
    if (tree && !Object.keys(open).length) setOpen(Object.fromEntries(tree.flatMap(n => [[n.uid, true], ...(n.children || []).map(c => [c.uid, true])])));
  }, [tree]);

  const flat = useMemo(() => { const out = []; const walk = n => { out.push(n); (n.children || []).forEach(walk); }; (tree || []).forEach(walk); return out; }, [tree]);
  const iterations = [...new Set(flat.map(n => n.iteration).filter(Boolean))].sort();
  const people = [...new Set(flat.map(n => n.assignee).filter(Boolean))].sort();
  const types = [...new Set(flat.map(n => n.req_type))];

  const matches = (n) => (!filters.type || n.req_type === filters.type)
    && (filters.status !== 'open' || !n.done) && (filters.status !== 'done' || n.done)
    && (!filters.iteration || (filters.iteration === '__none__' ? !n.iteration : n.iteration === filters.iteration))
    && (!filters.assignee || n.assignee === filters.assignee)
    && (!filters.text || `${n.id} ${n.title}`.toLowerCase().includes(filters.text.toLowerCase()));
  const filtering = filters.type || filters.status !== 'all' || filters.iteration || filters.assignee || filters.text;
  const keep = (n) => matches(n) || (n.children || []).some(keep);

  const move = async (uid, target, where) => {
    try {
      await api.work.rank(uid, target ? { [where]: target.uid } : {});
      load();
    } catch (err) { toast(err.message, 'error', 6000); }
  };
  const reparent = async (uid, parent) => {
    try { await api.requirements.update(uid, { parentId: parent.uid }); toast('Moved', 'success'); load(); }
    catch (err) { toast(err.message, 'error', 6000); }
  };

  const row = (n, depth) => {
    if (filtering && !keep(n)) return null;
    const kids = (n.children || []);
    const isOpen = open[n.uid] || (filtering && kids.some(keep));
    return [
      <tr key={n.uid} className={`${state.selectedUid === n.uid ? 'backlog-row--on' : ''} ${filtering && !matches(n) ? 'backlog-row--context' : ''}`}
        draggable={can('write')} onDragStart={() => { dragged.current = n; }}
        onDragOver={e => { if (dragged.current && dragged.current.uid !== n.uid) e.preventDefault(); }}
        onDrop={e => {
          e.preventDefault();
          const d = dragged.current; dragged.current = null;
          if (!d || d.uid === n.uid) return;
          const box = e.currentTarget.getBoundingClientRect();
          const third = (e.clientY - box.top) / box.height;
          if (third > 0.33 && third < 0.67) reparent(d.uid, n);
          else if ((d.parentId || null) === (n.parentId || null)) move(d.uid, n, third <= 0.33 ? 'before' : 'after');
          else toast('Drop on the middle of an item to move under it, or between items with the same parent to reorder', 'info', 5000);
        }}>
        <td>
          <div className="backlog-item" style={{ paddingLeft: depth * 20 }}>
            {kids.length ? <button className="backlog-toggle" aria-expanded={!!isOpen} aria-label={isOpen ? 'Collapse' : 'Expand'}
              onClick={() => setOpen(o => ({ ...o, [n.uid]: !isOpen }))}>{isOpen ? '▾' : '▸'}</button> : <span className="backlog-toggle" />}
            <button className="backlog-open" onClick={() => dispatch({ type: 'SELECT', uid: n.uid, artefactType: 'requirement' })}>
              <span className="mono work-id">{n.id}</span> {n.title}</button>
          </div>
        </td>
        <td>{labelOf.type(n.req_type, state.hierarchy)}</td>
        <td><span className={`work-pill ${n.done ? 'work-pill--done' : ''}`}>{labelOf.status(n.status, n.req_type, state.hierarchy)}</span></td>
        <td className="num">{n.estimate ?? (n.total_points ? `${n.done_points}/${n.total_points}` : '')}</td>
        <td>{n.assignee || ''}</td>
        <td>{n.iteration || ''}</td>
        <td>{n.linked_requirements > 0 ? n.linked_requirements
          : ['story', 'task', 'feature'].includes(n.req_type) ? <span className="work-pill work-pill--warn" title="Satisfies or implements no requirement">None</span> : ''}</td>
        <td>{n.progress_pct != null && kids.length > 0 && <span className="backlog-bar" title={`${n.progress_pct}% done`}>
          <span style={{ width: `${n.progress_pct}%` }} /></span>}{n.progress_pct != null && kids.length > 0 ? `${Math.round(n.progress_pct)}%` : ''}</td>
      </tr>,
      ...(isOpen ? kids.flatMap(c => row(c, depth + 1)) : []),
    ];
  };

  const create = async () => {
    const parent = flat.find(n => n.uid === state.selectedUid);
    const allowed = parent ? (state.hierarchy?.hierarchy?.[parent.req_type]?.allowed_children || []) : ['theme'];
    const req_type = allowed[0] || 'story';
    try {
      const item = await api.requirements.create({ title: `New ${labelOf.type(req_type, state.hierarchy).toLowerCase()}`, req_type,
        parentId: parent && allowed.length ? parent.uid : null });
      dispatch({ type: 'SELECT', uid: item.uid, artefactType: 'requirement' });
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const f = (k) => (e) => setFilters(x => ({ ...x, [k]: e.target.value }));
  return (
    <div className="work-backlog">
      <div className="work-filters">
        <label>Type<select value={filters.type} onChange={f('type')}><option value="">All work items</option>
          {types.map(t => <option key={t} value={t}>{labelOf.type(t, state.hierarchy)}</option>)}</select></label>
        <label>Status<select value={filters.status} onChange={f('status')}>
          <option value="open">Not done</option><option value="done">Done</option><option value="all">Any</option></select></label>
        <label>Iteration<select value={filters.iteration} onChange={f('iteration')}><option value="">Any</option>
          <option value="__none__">Not planned</option>{iterations.map(i => <option key={i} value={i}>{i}</option>)}</select></label>
        <label>Assignee<select value={filters.assignee} onChange={f('assignee')}><option value="">Anyone</option>
          {people.map(p => <option key={p} value={p}>{p}</option>)}</select></label>
        <label className="work-filter-text">Find<input type="search" value={filters.text} onChange={f('text')} placeholder="Id or title" /></label>
        <div className="work-filter-actions">
          <button className="btn btn-secondary" onClick={() => setOpen(Object.fromEntries(flat.map(n => [n.uid, true])))}>Expand all</button>
          {can('write') && <button className="btn btn-primary" onClick={create}>+ New work item</button>}
        </div>
      </div>
      <div className="work-split">
        <div className="backlog-table-wrap">
          {error && <div className="work-error" role="alert">{error}</div>}
          {!tree && !error && <div className="work-empty"><div className="spinner" /></div>}
          {tree && !tree.length && <div className="work-empty">No work items yet. Create a theme to start.</div>}
          {tree && tree.length > 0 && (
            <table className="backlog-table">
              <thead><tr><th>Item</th><th>Type</th><th>Status</th><th className="num">Points</th><th>Assignee</th><th>Iteration</th><th>Requirements</th><th>Progress</th></tr></thead>
              <tbody>{tree.flatMap(n => row(n, 0))}</tbody>
            </table>
          )}
          <p className="work-hint">Drag an item onto another to move it under it, or between two items with the same parent to reorder.</p>
        </div>
        {state.selectedUid && (
          <aside className="work-detail work-detail--editor" aria-label="Editor">
            <div className="editor-drawer-head"><span>Editing</span>
              <button className="btn btn-ghost" aria-label="Close editor" onClick={() => dispatch({ type: 'DESELECT' })}>✕</button></div>
            <div className="editor-drawer-body"><Editor /></div>
          </aside>
        )}
      </div>
    </div>
  );
}
