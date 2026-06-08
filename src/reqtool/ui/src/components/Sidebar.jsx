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
  const [showModulePanel, setShowModulePanel] = useState(false);
  const [availableModules, setAvailableModules] = useState([]);
  const [expandAll, setExpandAll] = useState(false);

  const load = useCallback(async () => {
    if (!activeProduct) return;
    setLoading(true); setError(null);
    try { setTree(await api.products.tree(activeProduct.id, activeVariant)); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, [activeProduct, activeVariant]);

  useEffect(() => { load(); }, [load]);

  const openModulePanel = async () => {
    try { const mods = await api.modules.list(); setAvailableModules(Array.isArray(mods) ? mods : []); }
    catch { setAvailableModules([]); }
    setShowModulePanel(true);
  };

  const filterNode = (node, q) => {
    const lq = q.toLowerCase();
    const match = node.id?.toLowerCase().includes(lq) || node.title?.toLowerCase().includes(lq);
    const kids  = (node.children || []).map(c => filterNode(c, q)).filter(Boolean);
    return (match || kids.length) ? { ...node, children: kids, _forceOpen: true } : null;
  };

  const displayTree = searchQuery ? tree.map(n => filterNode(n, searchQuery)).filter(Boolean) : tree;

  const createReq = async (parentId = null) => {
    try {
      const tmpl = state.pendingTemplate;
      const base = {
        title: tmpl ? `New ${tmpl.label}` : 'New requirement',
        parentId,
        content: tmpl?.fields?.content || { description: 'The system shall...', rationale: '', extended_description: '' },
        ...(tmpl?.fields || {}),
      };
      // Remove 'content' from top-level spread since it's already set
      delete base.fields;
      const req = await api.requirements.create(base);
      dispatch({ type: 'SELECT', uid: req.uid, artefactType: 'requirement' });
      if (tmpl) dispatch({ type: 'CLEAR_TEMPLATE' });
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

  if (!activeProduct) return (
    <div className="sidebar-empty">
      <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.4 }}>◈</div>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>No product selected</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 12, textAlign: 'center' }}>
        Use the product dropdown in the top bar to select a product, or create a new one with <strong>+ Product</strong>.
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6, background: 'var(--bg-elevated)', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)', textAlign: 'left' }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Don't have a repo yet?</div>
        Run from your terminal:<br />
        <code style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>req init demo</code><br />
        <code style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>req serve</code>
      </div>
    </div>
  );
  if (loading) return <div className="sidebar-loading"><div className="spinner" /></div>;
  if (error)   return <div className="sidebar-error">{error}</div>;

  return (
    <>
      {/* Toolbar */}
      <div className="tree-toolbar">
        <button className="btn btn-ghost tree-toolbar-btn" onClick={() => createReq()} title="New requirement">+ New</button>
        <button className="btn btn-ghost tree-toolbar-btn" onClick={openModulePanel}
          title="Include a shared requirement module in this product">⊕ Module</button>
        <div style={{ flex: 1 }} />
        <button className="btn btn-ghost tree-toolbar-btn"
          title={expandAll ? "Collapse all" : "Expand all"}
          onClick={() => setExpandAll(v => !v)}>
          {expandAll ? '⊟' : '⊞'}
        </button>
        <button className="btn btn-ghost tree-toolbar-btn" style={{ fontSize: 13 }} onClick={load} title="Refresh tree">↺</button>
      </div>
      {state.pendingTemplate && (
        <div className="tree-template-active">
          <span>◫ {state.pendingTemplate.label}</span>
          <button onClick={() => dispatch({ type: 'CLEAR_TEMPLATE' })} title="Cancel template">✕</button>
        </div>
      )}

      {/* Module include panel */}
      {showModulePanel && (
        <div className="module-include-panel">
          <div className="module-include-header">
            <span>Include a requirement module</span>
            <button className="btn btn-ghost" style={{ fontSize: 12, padding: '2px 6px' }}
              onClick={() => setShowModulePanel(false)}>✕</button>
          </div>
          <div className="module-include-hint">
            Modules are shared, versioned sets of requirements (e.g. a comms-security baseline)
            that appear in the tree labelled <span className="tree-module-pill" style={{ display: 'inline' }}>mod</span> and
            are managed independently of this product. Multiple products can include the same module.
          </div>
          {availableModules.length === 0 ? (
            <div className="module-include-empty">
              <div>No modules found in <code>modules/</code>.</div>
              <div style={{ marginTop: 4, fontSize: 11 }}>
                CLI: <code>req import &lt;module-id&gt; --product {activeProduct.id}</code>
              </div>
            </div>
          ) : availableModules.map(mod => {
            const alreadyIncluded = tree.some(n => n._is_module_group && n.module === mod.id);
            return (
              <div key={mod.id} className="module-include-item">
                <div className="module-include-item-meta">
                  <span className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{mod.id}</span>
                  <span style={{ fontSize: 12, fontWeight: 600, marginLeft: 8 }}>{mod.title || mod.id}</span>
                  {mod.version && <span style={{ fontSize: 11, color: 'var(--accent-blue)', marginLeft: 6 }}>v{mod.version}</span>}
                </div>
                {mod.description && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{mod.description}</div>}
                <button
                  className={`btn ${alreadyIncluded ? 'btn-secondary' : 'btn-primary'}`}
                  style={{ fontSize: 11, padding: '3px 10px', marginTop: 6 }}
                  disabled={alreadyIncluded}
                  onClick={async () => {
                    if (alreadyIncluded) return;
                    try {
                      await api.modules.include(activeProduct.id, mod.id);
                      await load();
                      toast(`Module '${mod.id}' included`, 'success');
                    } catch {
                      toast(`CLI: req import ${mod.id} --product ${activeProduct.id}`, 'info', 7000);
                    }
                    setShowModulePanel(false);
                  }}
                >
                  {alreadyIncluded ? '✓ Already included' : '⊕ Include'}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {!tree.length && !showModulePanel && (
        <div className="sidebar-empty">
          <div>No requirements yet.</div>
          <button className="btn btn-secondary" style={{ marginTop: 8, fontSize: 11 }} onClick={() => createReq()}>+ New requirement</button>
        </div>
      )}
      {searchQuery && !displayTree.length && <div className="sidebar-empty">No matches for <em>{searchQuery}</em></div>}

      <div className="tree-container" role="tree" onClick={() => setCtxMenu(null)}>
        {displayTree.map(node => (
          <TreeNode key={node.uid} node={node} forceOpen={expandAll || !!searchQuery}
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
  const [items, setItems]         = useState([]);
  const [loading, setLoading]     = useState(false);
  const [collapsed, setCollapsed] = useState({});
  const [search, setSearch]       = useState('');

  const load = () => { setLoading(true); api.principles.list().then(setItems).catch(() => {}).finally(() => setLoading(false)); };
  useEffect(() => { load(); }, []);

  const filtered = search ? items.filter(p => p.title?.toLowerCase().includes(search.toLowerCase()) || p.id?.toLowerCase().includes(search.toLowerCase())) : items;
  const grouped = {};
  for (const p of filtered) { const d = p.domain || 'unclassified'; if (!grouped[d]) grouped[d] = []; grouped[d].push(p); }
  const order = [...PRINCIPLE_DOMAIN_ORDER.filter(d => grouped[d]), ...Object.keys(grouped).filter(d => !PRINCIPLE_DOMAIN_ORDER.includes(d)).sort()];

  if (loading) return <div className="sidebar-loading"><div className="spinner" /></div>;
  return (
    <div className="list-panel">
      <div className="list-panel-toolbar">
        <input className="list-search" placeholder="Search principles..." value={search}
          onChange={e => setSearch(e.target.value)} />
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
            {t.status === 'open' || t.status === 'in_progress' ? (
              <button
                className="btn btn-ghost"
                style={{ fontSize: 10, padding: '1px 6px', marginLeft: 'auto' }}
                title="Mark as resolved"
                onClick={async e => {
                  e.stopPropagation();
                  try {
                    await api.tbds.resolve(t.uid, { resolution: 'Resolved via UI' });
                    load();
                    toast('TBD resolved', 'success');
                  } catch (err) { toast(err.message, 'error'); }
                }}>
                ✓ Resolve
              </button>
            ) : null}
          </div>
          <div className="list-item-title">{t.title}</div>
          {t.affected_requirements?.length > 0 && <div className="list-item-meta">{t.affected_requirements.length} affected reqs</div>}
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
// Task sidebar -- quick stats and sprint filter while kanban is open
// ---------------------------------------------------------------------------
function TaskSidebarPanel() {
  const { state, dispatch, toast } = useApp();
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.kanban.get({}).then(board => {
      if (!board) return;
      const cols = board.columns || {};
      const total = Object.values(cols).flat().length;
      const done  = (cols.done || []).length;
      const inProg = (cols.in_progress || []).length;
      const blocked = (cols.backlog || []).filter(c => c.priority === 'critical').length;
      setStats({ total, done, inProg, blocked, states: board.states || [] });
    }).catch(() => {});
  }, [state._lastCommit]);

  const createItem = async (req_type) => {
    try {
      const item = await api.requirements.create({ title: `New ${req_type}`, req_type });
      dispatch({ type: 'SELECT', uid: item.uid, artefactType: 'requirement' });
      toast(`Created ${item.id}`, 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  return (
    <div className="task-sidebar">
      <div className="task-sidebar-section">
        <div className="task-sidebar-label">Quick create</div>
        <div className="task-sidebar-actions">
          {[
            { icon: '📖', label: 'Story',   type: 'story' },
            { icon: '✅', label: 'Task',    type: 'task' },
            { icon: '🐛', label: 'Bug',     type: 'bug' },
            { icon: '🔬', label: 'Spike',   type: 'spike' },
          ].map(q => (
            <button key={q.type} className="task-quick-btn"
              onClick={() => createItem(q.type)}>
              <span>{q.icon}</span> {q.label}
            </button>
          ))}
        </div>
      </div>

      {stats && (
        <div className="task-sidebar-section">
          <div className="task-sidebar-label">Sprint snapshot</div>
          <div className="task-stats-grid">
            <div className="task-stat"><div className="task-stat-value">{stats.total}</div><div className="task-stat-label">Total</div></div>
            <div className="task-stat"><div className="task-stat-value" style={{ color: 'var(--accent-blue)' }}>{stats.inProg}</div><div className="task-stat-label">In progress</div></div>
            <div className="task-stat"><div className="task-stat-value" style={{ color: 'var(--accent-green)' }}>{stats.done}</div><div className="task-stat-label">Done</div></div>
            {stats.blocked > 0 && <div className="task-stat"><div className="task-stat-value" style={{ color: 'var(--accent-red)' }}>{stats.blocked}</div><div className="task-stat-label">Critical backlog</div></div>}
          </div>
        </div>
      )}

      <div className="task-sidebar-section">
        <div className="task-sidebar-hint">
          Drag cards between columns to update status. Click a card to open the editor.
          Press <kbd>Esc</kbd> to close the editor panel.
        </div>
      </div>
    </div>
  );
}

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

  return (
    <aside className="sidebar">
      <nav className="sidebar-sections">
        {TOP_SECTIONS.map(s => (
          <button key={s.id}
            className={`sidebar-section-tab ${topSection === s.id ? 'sidebar-section-tab--active' : ''}`}
            onClick={() => dispatch({ type: 'SET_PANEL', payload: s.id === 'tasks' ? 'tasks' : 'requirements' })}>
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

      {/* Task Mgmt: sidebar quick-actions */}
      {topSection === 'tasks' && (
        <div className="sidebar-content">
          <TaskSidebarPanel />
        </div>
      )}

      <div className="sidebar-content">
        {topSection === 'requirements' && panel === 'requirements' && <RequirementsPanel />}
        {topSection === 'requirements' && panel === 'principles'   && <PrinciplesPanel />}
        {topSection === 'requirements' && panel === 'tbds'         && <TBDsPanel />}
        {topSection === 'requirements' && panel === 'modules'      && <ModulesPanel />}
      </div>    </aside>
  );
}
