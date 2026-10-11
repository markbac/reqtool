/**
 * Sidebar.jsx
 * Two top-level sections:
 *   1. Requirements  -- sub-tabs: Reqs (product tree) | Principles | Decisions | Modules
 *   2. Task Mgmt     -- Kanban board (column-per-state, grouped by person or team)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';
import ResolveDialog from './ResolveDialog';
import { parentOf, candidateParents, canMoveUnder } from '../treeMove';
import { typeBody } from '../createItem';
import { PrinciplesPanel } from './Principles';
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

  const can = useCan();
  const items = [
    { label: '+ Add child',   action: 'add_child', needs: 'write' },
    { label: '+ Add sibling', action: 'add_sibling', needs: 'write' },
    { label: '⧉ Clone',       action: 'clone', needs: 'write' },
    { label: '⇄ Move to...',  action: 'move', needs: 'write' },
    { label: '⟳ History',     action: 'history' },
    { label: '✕ Delete',      action: 'delete', danger: true, needs: 'delete' },
  ].filter(i => !i.needs || can(i.needs));
  return (
    <div ref={ref} className="ctx-menu" style={{ top: y, left: x }}>
      {items.map(i => (
        <button key={i.action}
          className={`ctx-item ${i.danger ? 'ctx-item-danger' : ''}`}
          onClick={() => { onAction(node, i.action, { x, y }); onClose(); }}>
          {i.label}
        </button>
      ))}
    </div>
  );
}

// Which type a new child should have: offered by the server from the parent's type.
function ChildTypeMenu({ x, y, parent, types, onClose, onPick }) {
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [onClose]);
  return (
    <div ref={ref} className="ctx-menu" style={{ top: y, left: x }} role="menu" aria-label={`Add child to ${parent.id}`}>
      {types.map(t => (
        <button key={t} className="ctx-item" role="menuitem" onClick={() => { onPick(t); onClose(); }}>
          {TYPE_META[t]?.icon || '+'} {TYPE_META[t]?.label || t}
        </button>
      ))}
    </div>
  );
}

// Choose a new parent for ``node``. Targets the hierarchy does not allow are listed but disabled, with the reason.
function MovePicker({ node, tree, rules, parentUid, onClose, onPick }) {
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const rows = candidateParents(tree).filter(({ node: t }) =>
    !q || t.id?.toLowerCase().includes(q) || t.title?.toLowerCase().includes(q));
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-label={`Move ${node.id}`} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Move {node.id} to...</span>
          <button className="modal-close btn-ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">
          <input autoFocus className="move-search" placeholder="Search by ID or title..." aria-label="Search parents"
            value={query} onChange={e => setQuery(e.target.value)} />
          <ul className="move-list" role="listbox" aria-label="New parent">
            {!q && (
              <li>
                <button className="move-option" disabled={!parentUid} onClick={() => onPick(null)}
                  title={parentUid ? '' : `${node.id} is already at the top level`}>
                  <span className="move-id mono">(top level)</span>
                  <span className="move-title">No parent</span>
                </button>
              </li>
            )}
            {rows.map(({ node: t, depth }) => {
              const verdict = canMoveUnder(node, t, rules, parentUid);
              return (
                <li key={t.uid}>
                  <button className="move-option" role="option" aria-selected="false" disabled={!verdict.ok}
                    title={verdict.reason} style={{ paddingLeft: 10 + depth * 12 }} onClick={() => onPick(t)}>
                    <span className="move-id mono">{t.id}</span>
                    <span className="move-title">{t.title}</span>
                    {!verdict.ok && <span className="move-why">{verdict.reason}</span>}
                  </button>
                </li>
              );
            })}
            {q && rows.length === 0 && <li className="move-empty">No matches</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tree node
// ---------------------------------------------------------------------------
function TreeNode({ node, depth = 0, onContextMenu, forceOpen = false, dnd }) {
  const { state, dispatch } = useApp();
  const [open, setOpen] = useState(depth < 1 || forceOpen);
  const [dropHint, setDropHint] = useState(null);   // 'ok' | 'no' while something is dragged over
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
    if (!isModule) {
      if (state.dirtyUids.size > 0 && !state.dirtyUids.has(node.uid)) {
        if (!confirm('You have unsaved changes in your current editing session. Switch anyway?')) {
          return;
        }
      }
      dispatch({ type: 'SELECT', uid: node.uid, artefactType: 'requirement' });
    }
  };
  const keyDown = (e) => {
    if (isModule) return;
    if (e.key === 'Enter' || e.key === ' ')    { e.preventDefault(); dispatch({ type: 'SELECT', uid: node.uid, artefactType: 'requirement' }); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); setOpen(true); }
    else if (e.key === 'ArrowLeft')  { e.preventDefault(); setOpen(false); }
  };
  const draggable = !!dnd && !isModule && !node.module;
  const dragStart = (e) => {
    e.stopPropagation();
    e.dataTransfer?.setData?.('text/plain', node.uid);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
    dnd.start(node);
  };
  const dragOver = (e) => {
    if (!dnd || isModule || !dnd.dragging()) return;
    e.preventDefault(); e.stopPropagation();
    const ok = dnd.verdict(node).ok;
    if (e.dataTransfer) e.dataTransfer.dropEffect = ok ? 'move' : 'none';
    setDropHint(ok ? 'ok' : 'no');
  };
  const drop = (e) => {
    if (!dnd || !dnd.dragging()) return;
    e.preventDefault(); e.stopPropagation();
    setDropHint(null);
    dnd.drop(node);
  };
  const rightClick = (e) => {
    if (isModule) return;
    e.preventDefault(); e.stopPropagation();
    onContextMenu(e.clientX, e.clientY, node);
  };

  return (
    <div className="tree-node-wrapper">
      <div className={`tree-node ${isSelected ? 'tree-node--selected' : ''} ${isModule ? 'tree-node--module-group' : ''}${dropHint ? ` tree-node--drop-${dropHint}` : ''}`}
        style={{ paddingLeft: 12 + depth * 16, borderLeft: `3px solid ${accent}` }}
        onClick={click} onKeyDown={keyDown} onContextMenu={rightClick}
        draggable={draggable || undefined} onDragStart={draggable ? dragStart : undefined} onDragEnd={draggable ? () => dnd.end() : undefined}
        onDragOver={dragOver} onDragLeave={() => setDropHint(null)} onDrop={drop}
        role="treeitem" aria-selected={isSelected} aria-expanded={hasChildren ? open : undefined} tabIndex={0}>
        <span className="tree-node-toggle">
          {hasChildren ? (open ? '▾' : '▸') : <span style={{ opacity: 0 }}>▸</span>}
        </span>
        {meta.icon && <span className="tree-type-icon" title={meta.label}>{meta.icon}</span>}
        {isModule && <span className="tree-module-pill">mod</span>}
        <span className="tree-node-id mono">{node.id}</span>
        <span className="tree-node-title">{node.title}</span>
        {node.suspect_count > 0 && (
          <span className="tree-node-suspect" title={`${node.suspect_count} suspect link(s): an upstream item changed`}>⚠ {node.suspect_count}</span>
        )}
        {node.progress_pct != null && hasChildren && (
          <span className="tree-node-progress" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10 }}
            title={`${Math.round(node.progress_pct)}% of the work below is done`}>
            <span role="progressbar" aria-label={`${node.id} progress`} aria-valuenow={Math.round(node.progress_pct)} aria-valuemin={0} aria-valuemax={100}
              style={{ width: 34, height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden', display: 'inline-block' }}>
              <span style={{ display: 'block', height: '100%', width: `${node.progress_pct}%`, background: 'var(--accent-green, #238636)' }} />
            </span>{Math.round(node.progress_pct)}%
          </span>
        )}
        {isDirty && <span className="tree-node-dirty" title="Unsaved">●</span>}
        {!isModule && <StatusBadge status={node.status} />}
      </div>
      {open && hasChildren && (
        <div className="tree-children">
          {node.children.map(c => (
            <TreeNode key={c.uid} node={c} depth={depth + 1} onContextMenu={onContextMenu} forceOpen={forceOpen} dnd={dnd} />
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
  const can = useCan();
  const { activeProduct, activeVariant, searchQuery } = state;
  const [tree, setTree]       = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [ctxMenu, setCtxMenu] = useState(null);
  const [childMenu, setChildMenu] = useState(null);
  const [moving, setMoving] = useState(null);       // the node whose parent is being chosen
  const [rules, setRules] = useState(null);         // allowed_children per type, from the server
  const dragged = useRef(null);
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
  useEffect(() => {
    window.addEventListener('reqtool:tree-changed', load);
    return () => window.removeEventListener('reqtool:tree-changed', load);
  }, [load]);

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

  const createReq = async (parentId = null, reqType = null) => {
    try {
      const base = reqType ? typeBody(reqType, TYPE_META[reqType]?.label, parentId) : {
        title: 'New requirement',
        parentId,
        content: { description: 'The system shall...', rationale: '', extended_description: '' },
      };
      const req = await api.requirements.create(base);
      dispatch({ type: 'SELECT', uid: req.uid, artefactType: 'requirement' });
      await load(); return req;
    } catch (err) { toast(err.message, 'error'); return null; }
  };

  // Ask the server which types may sit under this one: one choice creates it, several open a menu.
  const addChild = async (node, pos) => {
    let types = [];
    try { types = (await api.hierarchy.children(node.req_type || 'functional'))?.allowed_children || []; }
    catch (err) { toast(err.message, 'error'); return; }
    if (types.length === 0) { toast(`${TYPE_META[node.req_type]?.label || node.req_type} items cannot have children`, 'info'); return; }
    if (types.length === 1) { await createReq(node.uid, types[0]); return; }
    setChildMenu({ x: pos?.x ?? 200, y: pos?.y ?? 200, node, types });
  };

  // The hierarchy rules decide which parents are offered; fetched when first needed.
  const loadRules = async () => {
    if (rules) return rules;
    try { const h = await api.hierarchy.get(); setRules(h.hierarchy || {}); return h.hierarchy || {}; }
    catch (err) { toast(err.message, 'error'); return null; }
  };

  // Re-parent ``node`` under ``target`` (a tree node, or null for the top level).
  const moveItem = async (node, target) => {
    if (state.dirtyUids.has(node.uid)) { toast(`Save or discard your changes to ${node.id} before moving it`, 'error'); return; }
    try {
      await api.requirements.update(node.uid, { parentId: target ? target.uid : null });
      window.dispatchEvent(new Event('reqtool:tree-changed'));
      window.dispatchEvent(new CustomEvent('reqtool:item-changed', { detail: { uid: node.uid } }));
      toast(target ? `Moved ${node.id} under ${target.id}` : `Moved ${node.id} to the top level`, 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  const dnd = {
    start: (node) => { dragged.current = node; loadRules(); },
    end: () => { dragged.current = null; },
    dragging: () => !!dragged.current,
    verdict: (target) => canMoveUnder(dragged.current, target, rules, parentOf(tree, dragged.current?.uid)?.uid ?? null),
    drop: async (target) => {
      const node = dragged.current; dragged.current = null;
      const known = rules || await loadRules();
      if (!node || !known) return;
      const verdict = canMoveUnder(node, target, known, parentOf(tree, node.uid)?.uid ?? null);
      if (!verdict.ok) { toast(verdict.reason, 'error'); return; }
      await moveItem(node, target);
    },
  };

  // Dropping on the empty part of the tree makes the item a top-level one.
  const dropOnTree = async (e) => {
    const node = dragged.current;
    if (!node || e.target !== e.currentTarget) return;
    e.preventDefault(); dragged.current = null;
    if (!parentOf(tree, node.uid)) { toast(`${node.id} is already at the top level`, 'info'); return; }
    await moveItem(node, null);
  };

  const handleCtx = async (node, action, pos) => {
    if (action === 'add_child')   { await addChild(node, pos); }
    else if (action === 'move') { if (await loadRules()) setMoving(node); }
    else if (action === 'add_sibling') {
      const full = await api.requirements.get(node.uid).catch(() => null);
      await createReq(full?.parentId || null, full?.req_type || node.req_type || null);
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
  if (loading && tree.length === 0) return <div className="sidebar-loading"><div className="spinner" /></div>;
  if (error)   return (
    <div className="sidebar-error">
      <div>{error}</div>
      <button className="btn btn-secondary" style={{ marginTop: 8, fontSize: 11 }} onClick={load}>Retry</button>
    </div>
  );

  return (
    <>
      {/* Toolbar */}
      <div className="tree-toolbar">
        {can('write') && <button className="btn btn-ghost tree-toolbar-btn" onClick={() => createReq()} title="New requirement">+ New</button>}
        {can('manage_modules') && <button className="btn btn-ghost tree-toolbar-btn" onClick={openModulePanel}
          title="Include a shared requirement module in this product">⊕ Module</button>}
        <div style={{ flex: 1 }} />
        <button className="btn btn-ghost tree-toolbar-btn"
          title={expandAll ? "Collapse all" : "Expand all"}
          onClick={() => setExpandAll(v => !v)}>
          {expandAll ? '⊟' : '⊞'}
        </button>
        <button className="btn btn-ghost tree-toolbar-btn" style={{ fontSize: 13 }} onClick={load} title="Refresh tree">↺</button>
      </div>

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
          {can('write') && <button className="btn btn-secondary" style={{ marginTop: 8, fontSize: 11 }} onClick={() => createReq()}>+ New requirement</button>}
        </div>
      )}
      {searchQuery && !displayTree.length && <div className="sidebar-empty">No matches for <em>{searchQuery}</em></div>}

      <div className="tree-container" role="tree" onClick={() => setCtxMenu(null)}
        onDragOver={(e) => { if (dragged.current && e.target === e.currentTarget) e.preventDefault(); }} onDrop={dropOnTree}>
        {displayTree.map(node => (
          <TreeNode key={node.uid} node={node} forceOpen={expandAll || !!searchQuery} dnd={dnd}
            onContextMenu={(x, y, n) => setCtxMenu({ x, y, node: n })} />
        ))}
      </div>
      {ctxMenu && <ContextMenu x={ctxMenu.x} y={ctxMenu.y} node={ctxMenu.node}
        onClose={() => setCtxMenu(null)} onAction={handleCtx} />}
      {moving && <MovePicker node={moving} tree={tree} rules={rules} parentUid={parentOf(tree, moving.uid)?.uid ?? null}
        onClose={() => setMoving(null)} onPick={(t) => { const n = moving; setMoving(null); moveItem(n, t); }} />}
      {childMenu && <ChildTypeMenu x={childMenu.x} y={childMenu.y} parent={childMenu.node} types={childMenu.types}
        onClose={() => setChildMenu(null)} onPick={(t) => createReq(childMenu.node.uid, t)} />}
      {histData && <HistoryOverlay uid={histUid} data={histData}
        onClose={() => { setHistData(null); setHistUid(null); }} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// 1c. Decisions: decisions, ADRs and open questions (TBDs) in one list
// ---------------------------------------------------------------------------
const KINDS = [['', 'All'], ['decision', 'Decisions & ADRs'], ['tbd', 'Open questions (TBD)']];
const OPEN_STATUSES = ['open', 'in_progress', 'proposed'];

function DecisionsList() {
  const can = useCan();
  const { state, dispatch, toast } = useApp();
  const [items, setItems]     = useState([]);
  const [kind, setKind]       = useState('');
  const [filter, setFilter]   = useState('');
  const [loading, setLoading] = useState(false);
  const [resolving, setResolving] = useState(null);
  const [newKind, setNewKind] = useState('decision');

  const load = useCallback(() => {
    setLoading(true);
    api.decisions.list(filter ? { status: filter } : {}).then(setItems).catch(() => {}).finally(() => setLoading(false));
  }, [filter]);
  useEffect(() => { load(); }, [load]);
  // Reload when something is saved elsewhere, so a resolved question moves on at once.
  useEffect(() => { load(); }, [state._lastCommit]);

  const shown = items.filter(d => !kind || (d.type || 'decision') === kind);

  const create = async () => {
    try {
      const body = newKind === 'tbd'
        ? { title: 'New open question', type: 'tbd', content: { description: '', impact: '', resolution_criteria: '', resolution: null } }
        : { title: 'New decision', content: { context: '', description: '', rationale: '' } };
      const t = newKind === 'tbd' ? await api.tbds.create(body) : await api.decisions.create(body);
      dispatch({ type: 'SELECT', uid: t.uid, artefactType: t.type || newKind });
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  return (
    <div className="tbds-panel" data-testid="decisions-list">
      {resolving && (
        <ResolveDialog tbd={resolving} onClose={() => setResolving(null)}
          onResolved={async body => {
            await api.tbds.resolve(resolving.uid, body);
            setResolving(null); load(); toast('Resolved into a decision', 'success');
          }} />
      )}
      <div className="list-panel-toolbar" style={{ gap: 4 }}>
        <select aria-label="Kind" value={kind} onChange={e => setKind(e.target.value)}>
          {KINDS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
        {can('write') && <>
          <select aria-label="New kind" value={newKind} onChange={e => setNewKind(e.target.value)}>
            <option value="decision">Decision</option><option value="tbd">Open question (TBD)</option>
          </select>
          <button className="btn btn-ghost list-new-btn" onClick={create}>+ New</button>
        </>}
      </div>
      <div className="tbds-filter">
        {['', 'open', 'in_progress', 'proposed', 'accepted', 'resolved'].map(s => (
          <button key={s} className={`tbds-filter-btn ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>{s ? s.replace('_', ' ') : 'all'}</button>
        ))}
      </div>
      {loading && <div className="sidebar-loading"><div className="spinner" /></div>}
      {!loading && !shown.length && <div className="sidebar-empty">Nothing here.</div>}
      {!loading && shown.map(t => (
        <div key={t.uid} className={`list-item ${state.selectedUid === t.uid ? 'list-item--selected' : ''}`}
          onClick={() => dispatch({ type: 'SELECT', uid: t.uid, artefactType: t.type === 'tbd' ? 'tbd' : 'decision' })}>
          <div className="list-item-header">
            <span className="list-item-id mono">{t.id}</span>
            <span className="badge" title={t.type === 'tbd' ? 'Open question' : 'Decision'}>{t.type === 'tbd' ? 'question' : 'decision'}</span>
            <span className={`badge badge-${t.status}`}>{t.status}</span>
            {t.type === 'tbd' && OPEN_STATUSES.includes(t.status) && can('write') ? (
              <button
                className="btn btn-ghost"
                style={{ fontSize: 10, padding: '1px 6px', marginLeft: 'auto' }}
                title="Resolve into a decision"
                onClick={e => { e.stopPropagation(); setResolving(t); }}>
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
            { icon: '🎯', label: 'Theme',      type: 'theme' },
            { icon: '🚀', label: 'Initiative', type: 'initiative' },
            { icon: '📦', label: 'Epic',       type: 'epic' },
            { icon: '✨', label: 'Feature',    type: 'feature' },
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
  { id: 'decisions',    label: 'Decisions'  },
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
        {topSection === 'requirements' && panel === 'decisions'    && <DecisionsList />}
        {topSection === 'requirements' && panel === 'modules'      && <ModulesPanel />}
      </div>    </aside>
  );
}
