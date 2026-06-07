/**
 * Sidebar.jsx
 * Two top-level sections:
 *   1. Requirements  -- sub-tabs: Reqs (product tree) | Principles | TBDs | Modules
 *   2. Task Mgmt     -- Kanban board (column-per-state, grouped by person or team)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import './Sidebar.css';

const DOMAIN_COLOURS = {
  need: '#64748b', sensing: '#0ea5e9', comms: '#a855f7', power: '#f59e0b',
  mechanical: '#f97316', thermal: '#fb7185', industrial: '#e879f9',
  security: '#e11d48', safety: '#fcd34d', compliance: '#475569',
  ux: '#10b981', manufacture: '#84cc16', identity: '#06b6d4',
  firmware: '#8b5cf6', data: '#f472b6', cost: '#34d399', system: '#94a3b8',
};

const TYPE_META = {
  theme:           { icon: '🎯', colour: '#6e40c9', label: 'Theme' },
  initiative:      { icon: '🚀', colour: '#1f6feb', label: 'Initiative' },
  epic:            { icon: '📦', colour: '#388bfd', label: 'Epic' },
  feature:         { icon: '✨', colour: '#56d364', label: 'Feature' },
  story:           { icon: '📖', colour: '#79c0ff', label: 'Story' },
  task:            { icon: '✅', colour: '#d2a8ff', label: 'Task' },
  bug:             { icon: '🐛', colour: '#ff7b72', label: 'Bug' },
  spike:           { icon: '🔬', colour: '#ffa657', label: 'Spike' },
  stakeholder_need:{ icon: '👤', colour: '#e3b341', label: 'Stakeholder Need' },
  functional:      { icon: '⚙️',  colour: '#388bfd', label: 'Functional' },
  performance:     { icon: '📈', colour: '#56d364', label: 'Performance' },
  security:        { icon: '🔒', colour: '#ff7b72', label: 'Security' },
  safety:          { icon: '⚠️',  colour: '#ffa657', label: 'Safety' },
  interface:       { icon: '🔌', colour: '#79c0ff', label: 'Interface' },
  compliance:      { icon: '📋', colour: '#e3b341', label: 'Compliance' },
  constraint:      { icon: '🚧', colour: '#8b949e', label: 'Constraint' },
  operational:     { icon: '🏭', colour: '#d2a8ff', label: 'Operational' },
  physical:        { icon: '📐', colour: '#6e40c9', label: 'Physical' },
};

const AGILE_TYPES = ['theme', 'initiative', 'epic', 'feature', 'story', 'task', 'bug', 'spike'];

function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

// ---------------------------------------------------------------------------
// Context menu
// ---------------------------------------------------------------------------
function ContextMenu({ x, y, node, onClose, onAction }) {
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [onClose]);

  const items = [
    { label: '+ Add child',   action: 'add_child' },
    { label: '+ Add sibling', action: 'add_sibling' },
    { label: '⧉ Clone',       action: 'clone' },
    { label: '⟳ History',     action: 'history' },
    { label: '✕ Delete',      action: 'delete', danger: true },
  ];
  return (
    <div ref={ref} className="ctx-menu" style={{ top: y, left: x }}>
      {items.map(i => (
        <button key={i.action}
          className={`ctx-item ${i.danger ? 'ctx-item-danger' : ''}`}
          onClick={() => { onAction(node, i.action); onClose(); }}>
          {i.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tree node
// ---------------------------------------------------------------------------
function TreeNode({ node, depth = 0, onContextMenu, forceOpen = false }) {
  const { state, dispatch } = useApp();
  const [open, setOpen] = useState(depth < 1 || forceOpen);
  const hasChildren = node.children?.length > 0;
  const isSelected  = state.selectedUid === node.uid;
  const isDirty     = state.dirtyUids.has(node.uid);
  const isModule    = node._is_module_group;
  const meta        = TYPE_META[node.req_type] || {};
  const accent      = meta.colour || (node.domain ? (DOMAIN_COLOURS[node.domain] || 'transparent') : 'transparent');

  useEffect(() => { if (forceOpen) setOpen(true); }, [forceOpen]);

  const click = (e) => {
    e.stopPropagation();
    if (hasChildren) setOpen(o => !o);
    if (!isModule) dispatch({ type: 'SELECT', uid: node.uid, artefactType: 'requirement' });
  };
  const keyDown = (e) => {
    if (isModule) return;
    if (e.key === 'Enter' || e.key === ' ')    { e.preventDefault(); dispatch({ type: 'SELECT', uid: node.uid, artefactType: 'requirement' }); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); setOpen(true); }
    else if (e.key === 'ArrowLeft')  { e.preventDefault(); setOpen(false); }
  };
  const rightClick = (e) => {
    if (isModule) return;
    e.preventDefault(); e.stopPropagation();
    onContextMenu(e.clientX, e.clientY, node);
  };

  return (
    <div className="tree-node-wrapper">
      <div className={`tree-node ${isSelected ? 'tree-node--selected' : ''} ${isModule ? 'tree-node--module-group' : ''}`}
        style={{ paddingLeft: 12 + depth * 16, borderLeft: `3px solid ${accent}` }}
        onClick={click} onKeyDown={keyDown} onContextMenu={rightClick}
        role="treeitem" aria-selected={isSelected} aria-expanded={hasChildren ? open : undefined} tabIndex={0}>
        <span className="tree-node-toggle">
          {hasChildren ? (open ? '▾' : '▸') : <span style={{ opacity: 0 }}>▸</span>}
        </span>
        {meta.icon && <span className="tree-type-icon" title={meta.label}>{meta.icon}</span>}
        {isModule && <span className="tree-module-pill">mod</span>}
        <span className="tree-node-id mono">{node.id}</span>
        <span className="tree-node-title">{node.title}</span>
        {isDirty && <span className="tree-node-dirty" title="Unsaved">●</span>}
        {!isModule && <StatusBadge status={node.status} />}
      </div>
      {open && hasChildren && (
        <div className="tree-children">
          {node.children.map(c => (
            <TreeNode key={c.uid} node={c} depth={depth + 1} onContextMenu={onContextMenu} forceOpen={forceOpen} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// History overlay
// ---------------------------------------------------------------------------
function HistoryOverlay({ uid, data, onClose }) {
  return (
    <div className="history-overlay" onClick={onClose}>
      <div className="history-panel" onClick={e => e.stopPropagation()}>
        <div className="history-panel-header">
          <span>History: {uid}</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="history-panel-body">
          {data.in_file?.map((h, i) => (
            <div key={i} className="hist-row">
              <span className="mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>v{h.version}</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{h.date?.slice(0, 10)}</span>
              <span style={{ fontSize: 12 }}>{h.summary}</span>
              {h.commit_sha && <span className="mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{h.commit_sha}</span>}
            </div>
          ))}
          {data.git?.map((g, i) => (
            <div key={`g${i}`} className="hist-row" style={{ borderTop: i === 0 ? '1px solid var(--border)' : undefined }}>
              <span className="mono" style={{ fontSize: 10, color: 'var(--accent-blue)' }}>{g.sha?.slice(0, 7)}</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{g.date?.slice(0, 10)}</span>
              <span style={{ fontSize: 12 }}>{g.subject}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1a. Requirements tree panel
// ---------------------------------------------------------------------------
function RequirementsPanel() {
  const { state, dispatch, toast } = useApp();
  const { activeProduct, activeVariant, searchQuery } = state;
  const [tree, setTree]       = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [ctxMenu, setCtxMenu] = useState(null);
  const [histUid, setHistUid] = useState(null);
  const [histData, setHistData] = useState(null);

  const load = useCallback(async () => {
    if (!activeProduct) return;
    setLoading(true); setError(null);
    try { setTree(await api.products.tree(activeProduct.id, activeVariant)); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, [activeProduct, activeVariant]);

  useEffect(() => { load(); }, [load]);

  const filterNode = (node, q) => {
    const lq = q.toLowerCase();
    const match = node.id?.toLowerCase().includes(lq) || node.title?.toLowerCase().includes(lq);
    const kids  = (node.children || []).map(c => filterNode(c, q)).filter(Boolean);
    return (match || kids.length) ? { ...node, children: kids, _forceOpen: true } : null;
  };

  const displayTree = searchQuery ? tree.map(n => filterNode(n, searchQuery)).filter(Boolean) : tree;

  const createReq = async (parentId = null) => {
    try {
      const req = await api.requirements.create({
        title: 'New requirement', parentId,
        content: { description: 'The system shall...', rationale: '', extended_description: '' },
      });
      dispatch({ type: 'SELECT', uid: req.uid, artefactType: 'requirement' });
      await load(); return req;
    } catch (err) { toast(err.message, 'error'); return null; }
  };

  const handleCtx = async (node, action) => {
    if (action === 'add_child')   { await createReq(node.uid); }
    else if (action === 'add_sibling') {
      const full = await api.requirements.get(node.uid).catch(() => null);
      await createReq(full?.parentId || null);
    } else if (action === 'clone') {
      try { const c = await api.requirements.clone(node.uid); dispatch({ type: 'SELECT', uid: c.uid, artefactType: 'requirement' }); await load(); toast(`Cloned as ${c.id}`, 'success'); }
      catch (err) { toast(err.message, 'error'); }
    } else if (action === 'delete') {
      if (!confirm(`Delete ${node.id}?`)) return;
      try { await api.requirements.delete(node.uid); dispatch({ type: 'DESELECT' }); await load(); toast('Deleted', 'info'); }
      catch (err) { toast(err.message, 'error'); }
    } else if (action === 'history') {
      try { const h = await api.requirements.history(node.uid); setHistUid(node.id); setHistData(h); }
      catch (err) { toast(err.message, 'error'); }
    }
  };

  if (!activeProduct) return <div className="sidebar-empty">Select a product above to view requirements.</div>;
  if (loading) return <div className="sidebar-loading"><div className="spinner" /></div>;
  if (error)   return <div className="sidebar-error">{error}</div>;
  if (!tree.length) return (
    <div className="sidebar-empty">
      <div>No requirements found.</div>
      <button className="btn btn-secondary" style={{ marginTop: 8, fontSize: 11 }} onClick={() => createReq()}>+ New requirement</button>
    </div>
  );
  if (searchQuery && !displayTree.length) return <div className="sidebar-empty">No matches for <em>{searchQuery}</em></div>;

  return (
    <>
      <div className="tree-container" role="tree" onClick={() => setCtxMenu(null)}>
        {displayTree.map(node => (
          <TreeNode key={node.uid} node={node} forceOpen={!!searchQuery}
            onContextMenu={(x, y, n) => setCtxMenu({ x, y, node: n })} />
        ))}
      </div>
      {ctxMenu && <ContextMenu x={ctxMenu.x} y={ctxMenu.y} node={ctxMenu.node}
        onClose={() => setCtxMenu(null)} onAction={handleCtx} />}
      {histData && <HistoryOverlay uid={histUid} data={histData}
        onClose={() => { setHistData(null); setHistUid(null); }} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// 1b. Principles panel
// ---------------------------------------------------------------------------
const PRINCIPLE_DOMAIN_ORDER = ['business', 'architecture', 'security', 'firmware', 'comms', 'data', 'process', 'safety'];

function PrinciplesPanel() {
  const { state, dispatch, toast } = useApp();
  const [items, setItems]       = useState([]);
  const [loading, setLoading]   = useState(false);
  const [collapsed, setCollapsed] = useState({});

  const load = () => { setLoading(true); api.principles.list().then(setItems).catch(() => {}).finally(() => setLoading(false)); };
  useEffect(() => { load(); }, []);

  const grouped = {};
  for (const p of items) { const d = p.domain || 'unclassified'; if (!grouped[d]) grouped[d] = []; grouped[d].push(p); }
  const order = [...PRINCIPLE_DOMAIN_ORDER.filter(d => grouped[d]), ...Object.keys(grouped).filter(d => !PRINCIPLE_DOMAIN_ORDER.includes(d)).sort()];

  if (loading) return <div className="sidebar-loading"><div className="spinner" /></div>;
  return (
    <div className="list-panel">
      <div className="list-panel-toolbar">
        <button className="btn btn-ghost list-new-btn" onClick={async () => {
          try { const p = await api.principles.create({ title: 'New principle', content: { description: '', rationale: '', implications: '', exceptions: '' } }); dispatch({ type: 'SELECT', uid: p.uid, artefactType: 'principle' }); load(); }
          catch (err) { toast(err.message, 'error'); }
        }}>+ New</button>
      </div>
      {!items.length && <div className="sidebar-empty">No principles defined.</div>}
      {order.map(domain => {
        const domainItems = grouped[domain] || [];
        const colour = DOMAIN_COLOURS[domain] || 'var(--text-muted)';
        return (
          <div key={domain} className="principle-group">
            <button className="principle-group-header"
              onClick={() => setCollapsed(c => ({ ...c, [domain]: !c[domain] }))}
              style={{ borderLeft: `3px solid ${colour}` }}>
              <span className="principle-group-toggle">{collapsed[domain] ? '▸' : '▾'}</span>
              <span className="principle-group-label">{domain}</span>
              <span className="principle-group-count">{domainItems.length}</span>
            </button>
            {!collapsed[domain] && domainItems.map(p => (
              <div key={p.uid} className={`list-item ${state.selectedUid === p.uid ? 'list-item--selected' : ''}`}
                style={{ borderLeft: `3px solid ${colour}`, paddingLeft: 20 }}
                onClick={() => dispatch({ type: 'SELECT', uid: p.uid, artefactType: 'principle' })}>
                <div className="list-item-header">
                  <span className="list-item-id mono">{p.id}</span>
                  <span className={`badge badge-${p.approval?.status ?? p.status ?? 'draft'}`}>{p.approval?.status ?? p.status ?? 'draft'}</span>
                </div>
                <div className="list-item-title">{p.title}</div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1c. TBDs panel
// ---------------------------------------------------------------------------
function TBDsPanel() {
  const { state, dispatch, toast } = useApp();
  const [items, setItems]     = useState([]);
  const [filter, setFilter]   = useState('open');
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.tbds.list(filter ? { status: filter } : {}).then(setItems).catch(() => {}).finally(() => setLoading(false));
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="tbds-panel">
      <div className="list-panel-toolbar">
        <button className="btn btn-ghost list-new-btn" onClick={async () => {
          try { const t = await api.tbds.create({ title: 'New TBD', content: { description: '', impact: '', resolution_criteria: '', resolution: null } }); dispatch({ type: 'SELECT', uid: t.uid, artefactType: 'tbd' }); load(); }
          catch (err) { toast(err.message, 'error'); }
        }}>+ New</button>
      </div>
      <div className="tbds-filter">
        {['', 'open', 'in_progress', 'resolved', 'cancelled'].map(s => (
          <button key={s} className={`tbds-filter-btn ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>{s || 'all'}</button>
        ))}
      </div>
      {loading && <div className="sidebar-loading"><div className="spinner" /></div>}
      {!loading && !items.length && <div className="sidebar-empty">No TBDs.</div>}
      {!loading && items.map(t => (
        <div key={t.uid} className={`list-item ${state.selectedUid === t.uid ? 'list-item--selected' : ''}`}
          onClick={() => dispatch({ type: 'SELECT', uid: t.uid, artefactType: 'tbd' })}>
          <div className="list-item-header">
            <span className="list-item-id mono">{t.id}</span>
            <span className={`badge badge-${t.status}`}>{t.status}</span>
          </div>
          <div className="list-item-title">{t.title}</div>
          {t.affected_requirements?.length > 0 && <div className="list-item-meta">{t.affected_requirements.length} affected</div>}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1d. Modules panel -- module library, independent of products
// ---------------------------------------------------------------------------
function ModulesPanel() {
  const { state, dispatch } = useApp();
  const [modules, setModules]   = useState([]);
  const [selected, setSelected] = useState(null);
  const [moduleReqs, setModuleReqs] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [loadingReqs, setLoadingReqs] = useState(false);

  const loadModules = () => {
    setLoading(true);
    api.modules.list().then(d => setModules(Array.isArray(d) ? d : [])).catch(() => setModules([])).finally(() => setLoading(false));
  };
  useEffect(() => { loadModules(); }, []);

  const selectModule = async (mod) => {
    setSelected(mod); setLoadingReqs(true);
    try { const d = await api.modules.get(mod.id); setModuleReqs(d.requirements || []); }
    catch { setModuleReqs([]); }
    finally { setLoadingReqs(false); }
  };

  if (loading) return <div className="sidebar-loading"><div className="spinner" /></div>;
  if (!modules.length) return (
    <div className="sidebar-empty">
      <div>No modules found.</div>
      <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
        Add a <code>modules/</code> directory with module manifests to use shared requirement sets.
      </div>
    </div>
  );

  return (
    <div className="modules-panel">
      <div className="modules-list">
        {modules.map(mod => (
          <button key={mod.id}
            className={`module-item ${selected?.id === mod.id ? 'module-item--selected' : ''}`}
            onClick={() => selectModule(mod)}>
            <span className="module-item-id mono">{mod.id}</span>
            <span className="module-item-title">{mod.title || mod.id}</span>
            {mod.version && <span className="module-item-version">v{mod.version}</span>}
          </button>
        ))}
      </div>
      {selected && (
        <div className="module-reqs">
          <div className="module-reqs-header">
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{selected.id}</span>
            <span style={{ fontSize: 12, fontWeight: 600 }}>{selected.title || selected.id}</span>
            {selected.version && <span style={{ fontSize: 11, color: 'var(--accent-blue)' }}>v{selected.version}</span>}
          </div>
          {loadingReqs && <div className="sidebar-loading"><div className="spinner" /></div>}
          {!loadingReqs && !moduleReqs.length && <div className="sidebar-empty" style={{ padding: 8 }}>No requirements in module.</div>}
          {!loadingReqs && moduleReqs.map(req => (
            <div key={req.uid}
              className={`list-item ${state.selectedUid === req.uid ? 'list-item--selected' : ''}`}
              onClick={() => dispatch({ type: 'SELECT', uid: req.uid, artefactType: 'requirement' })}>
              <div className="list-item-header">
                <span className="list-item-id mono">{req.id}</span>
                <StatusBadge status={req.status} />
              </div>
              <div className="list-item-title">{req.title}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 2. Kanban panel -- column-per-state, grouped by person or team
// ---------------------------------------------------------------------------
const KANBAN_GROUPINGS = [
  { id: 'assignee', label: 'By Person' },
  { id: 'owner',    label: 'By Team'   },
  { id: 'none',     label: 'All'       },
];

function KanbanCard({ card, isSelected, onClick }) {
  const meta = TYPE_META[card.req_type] || {};
  return (
    <div className={`kanban-card ${isSelected ? 'kanban-card--selected' : ''}`}
      style={{ borderLeft: `3px solid ${meta.colour || 'var(--border)'}` }}
      onClick={onClick} title={card.title}>
      <div className="kanban-card-header">
        <span className="kanban-card-id mono">{card.id}</span>
        {meta.icon && <span className="kanban-card-icon">{meta.icon}</span>}
        {card.estimate != null && <span className="kanban-card-est">{card.estimate}</span>}
      </div>
      <div className="kanban-card-title">{card.title}</div>
      <div className="kanban-card-meta">
        {card.assignee  && <span className="kanban-pill">👤 {card.assignee}</span>}
        {card.iteration && <span className="kanban-pill">🔁 {card.iteration}</span>}
        {card.priority && card.priority !== 'medium' && (
          <span className={`kanban-pill priority-${card.priority}`}>{card.priority}</span>
        )}
      </div>
    </div>
  );
}

function KanbanPanel() {
  const { state, dispatch, toast } = useApp();
  const [board, setBoard]             = useState(null);
  const [loading, setLoading]         = useState(false);
  const [groupBy, setGroupBy]         = useState('assignee');
  const [typeFilter, setTypeFilter]   = useState('');
  const [iterFilter, setIterFilter]   = useState('');
  const [personFilter, setPersonFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (typeFilter)   params.req_type  = typeFilter;
      if (iterFilter)   params.iteration = iterFilter;
      if (personFilter) params.assignee  = personFilter;
      setBoard(await api.kanban.get(params));
    } catch { setBoard(null); }
    finally { setLoading(false); }
  }, [typeFilter, iterFilter, personFilter]);

  useEffect(() => { load(); }, [load]);

  const allCards = board ? Object.values(board.columns || {}).flat() : [];

  // Build swimlane groups
  const getGroups = () => {
    if (!board || groupBy === 'none') return null; // null = no swimlanes
    const groups = {};
    for (const card of allCards) {
      const key = groupBy === 'assignee'
        ? (card.assignee || '(unassigned)')
        : (card.owner    || '(no owner)');
      if (!groups[key]) groups[key] = new Set();
      groups[key].add(card.uid);
    }
    return groups; // group label -> Set of uids in that group
  };

  const groups   = getGroups();
  const states   = board?.states || [];
  const colCards = (stateId) => board?.columns?.[stateId] || [];

  const createItem = async () => {
    try {
      const item = await api.requirements.create({ title: 'New story', req_type: typeFilter || 'story' });
      dispatch({ type: 'SELECT', uid: item.uid, artefactType: 'requirement' });
      await load(); toast(`Created ${item.id}`, 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  return (
    <div className="kanban-panel">
      {/* Toolbar */}
      <div className="kanban-toolbar">
        <div className="kanban-grouping">
          {KANBAN_GROUPINGS.map(g => (
            <button key={g.id}
              className={`kanban-group-btn ${groupBy === g.id ? 'kanban-group-btn--active' : ''}`}
              onClick={() => setGroupBy(g.id)}>
              {g.label}
            </button>
          ))}
        </div>
        <div className="kanban-filters">
          <select className="kanban-select" value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}>
            <option value="">All types</option>
            {AGILE_TYPES.map(t => (
              <option key={t} value={t}>{TYPE_META[t]?.label || t}</option>
            ))}
          </select>
          <input className="kanban-filter-input" placeholder="Iteration…"
            value={iterFilter} onChange={e => setIterFilter(e.target.value)} />
          <input className="kanban-filter-input" placeholder="Person…"
            value={personFilter} onChange={e => setPersonFilter(e.target.value)} />
          <button className="btn btn-ghost kanban-new-btn" onClick={createItem} title="New item">+</button>
        </div>
      </div>

      {loading && <div className="sidebar-loading"><div className="spinner" /></div>}
      {!loading && !board && <div className="sidebar-empty">Could not load board.</div>}

      {!loading && board && (
        <div className="kanban-body">
          <div className="kanban-columns">
            {states.map(stateId => (
              <div key={stateId} className="kanban-col">
                <div className="kanban-col-header">
                  <span className="kanban-col-label">{stateId.replace(/_/g, '\u00A0')}</span>
                  <span className="kanban-col-count">{colCards(stateId).length}</span>
                </div>
                <div className="kanban-col-body">
                  {/* No swimlanes: render all cards for this state */}
                  {!groups && colCards(stateId).map(card => (
                    <KanbanCard key={card.uid} card={card}
                      isSelected={state.selectedUid === card.uid}
                      onClick={() => dispatch({ type: 'SELECT', uid: card.uid, artefactType: 'requirement' })} />
                  ))}

                  {/* Swimlanes: render one section per group */}
                  {groups && Object.entries(groups).map(([groupLabel, uidSet]) => {
                    const groupColCards = colCards(stateId).filter(c => uidSet.has(c.uid));
                    return (
                      <div key={groupLabel} className="kanban-swimlane">
                        <div className="kanban-swimlane-label">{groupLabel}</div>
                        {groupColCards.length === 0
                          ? <div className="kanban-swimlane-empty" />
                          : groupColCards.map(card => (
                              <KanbanCard key={card.uid} card={card}
                                isSelected={state.selectedUid === card.uid}
                                onClick={() => dispatch({ type: 'SELECT', uid: card.uid, artefactType: 'requirement' })} />
                            ))
                        }
                      </div>
                    );
                  })}

                  {colCards(stateId).length === 0 && !groups && (
                    <div className="kanban-col-empty" />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sidebar root
// ---------------------------------------------------------------------------

const TOP_SECTIONS = [
  { id: 'requirements', label: 'Requirements' },
  { id: 'tasks',        label: 'Task Mgmt'    },
];

const REQ_SUBTABS = [
  { id: 'requirements', label: 'Reqs'       },
  { id: 'principles',   label: 'Principles' },
  { id: 'tbds',         label: 'TBDs'       },
  { id: 'modules',      label: 'Modules'    },
];

export default function Sidebar() {
  const { state, dispatch } = useApp();
  const { panel } = state;

  const topSection = panel === 'tasks' ? 'tasks' : 'requirements';

  const setTopSection = (id) => {
    dispatch({ type: 'SET_PANEL', payload: id === 'tasks' ? 'tasks' : 'requirements' });
  };

  return (
    <aside className="sidebar">
      <nav className="sidebar-sections">
        {TOP_SECTIONS.map(s => (
          <button key={s.id}
            className={`sidebar-section-tab ${topSection === s.id ? 'sidebar-section-tab--active' : ''}`}
            onClick={() => setTopSection(s.id)}>
            {s.label}
          </button>
        ))}
      </nav>

      {topSection === 'requirements' && (
        <nav className="sidebar-tabs">
          {REQ_SUBTABS.map(t => (
            <button key={t.id}
              className={`sidebar-tab ${panel === t.id ? 'sidebar-tab--active' : ''}`}
              onClick={() => dispatch({ type: 'SET_PANEL', payload: t.id })}>
              {t.label}
            </button>
          ))}
        </nav>
      )}

      <div className="sidebar-content">
        {topSection === 'requirements' && panel === 'requirements' && <RequirementsPanel />}
        {topSection === 'requirements' && panel === 'principles'   && <PrinciplesPanel />}
        {topSection === 'requirements' && panel === 'tbds'         && <TBDsPanel />}
        {topSection === 'requirements' && panel === 'modules'      && <ModulesPanel />}
        {topSection === 'tasks'                                    && <KanbanPanel />}
      </div>
    </aside>
  );
}
