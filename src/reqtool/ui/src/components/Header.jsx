/**
 * Header.jsx -- Top bar.
 * - Product/variant selector
 * - Live search (dispatches SET_SEARCH)
 * - Git status polling every 10s, refresh on commit
 * - Staged badge is clickable -> global commit modal
 * - Action buttons: Validate, Coverage, Bulk, Export
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';
import './Header.css';

function UserIdentityWidget({ onLogin }) {
  const { state } = useApp();
  const currentUser = state.enums?._current_user || localStorage.getItem('reqtool:username') || 'user';

  return (
    <button
      className="btn btn-ghost"
      style={{ fontSize: 11, padding: '3px 7px', color: 'var(--text-muted)' }}
      onClick={onLogin}
      title="User Identity & Server Connection (Click to login or switch server)"
    >👤 {currentUser}</button>
  );
}

/** The "More" menu: grouped under headings, searchable, and operable from the keyboard (arrows, Home, End, Esc). */
function OverflowMenu({ groups }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef(null);
  const search = useRef(null);
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);
  useEffect(() => { if (open) search.current?.focus(); else setQuery(''); }, [open]);

  const q = query.trim().toLowerCase();
  const shown = groups
    .map(g => ({ ...g, items: g.items.filter(i => !q || i.label.toLowerCase().includes(q) || g.heading.toLowerCase().includes(q)) }))
    .filter(g => g.items.length);

  const items = () => Array.from(ref.current?.querySelectorAll('[role="menuitem"]') || []);
  const onKey = (e) => {
    const list = items();
    const at = list.indexOf(document.activeElement);
    if (e.key === 'Escape') { setOpen(false); ref.current?.querySelector('button')?.focus(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); list[Math.min(list.length - 1, at + 1)]?.focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); if (at <= 0) search.current?.focus(); else list[at - 1]?.focus(); }
    else if (e.key === 'Home' && at >= 0) { e.preventDefault(); list[0]?.focus(); }
    else if (e.key === 'End' && at >= 0) { e.preventDefault(); list[list.length - 1]?.focus(); }
  };
  const run = (item) => { item.action?.(); setOpen(false); };
  return (
    <div ref={ref} style={{ position: 'relative' }} onKeyDown={open ? onKey : undefined}>
      <button className="btn btn-ghost header-action-btn" onClick={() => setOpen(v => !v)} title="More tools"
        aria-haspopup="menu" aria-expanded={open}>⋯ More</button>
      {open && (
        <div className="overflow-menu" role="menu" aria-label="More tools">
          <input ref={search} className="overflow-menu-search" type="search" placeholder="Find a tool…" aria-label="Find a tool"
            value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && shown[0]) { e.preventDefault(); run(shown[0].items[0]); } }} />
          {shown.map(g => (
            <div key={g.heading} role="group" aria-label={g.heading}>
              <div className="overflow-menu-heading" role="presentation">{g.heading}</div>
              {g.items.map(item => (
                <button key={item.label} role="menuitem" className="overflow-menu-item" onClick={() => run(item)}>{item.label}</button>
              ))}
            </div>
          ))}
          {!shown.length && <div className="overflow-menu-empty">Nothing matches "{query}".</div>}
        </div>
      )}
    </div>
  );
}

export default function Header({ onValidate, onExport, onCoverage, onBulk, onVocabularies,
                               onBaselines, onMetrics, onImport, onTraceability, onGlobalCommit,
                               onCustomFields, onWebhooks, onToggleSidebar, onHelp, onRepo, onLogin, onDiagram, onIterations,
                               onAutomation, onDuplicateDetector, onTemplates,
                               onOverview, onRoadmap, onDecisions, onModules, onChangeSets, onInbox, onQuery }) {
  const { state, dispatch, toast } = useApp();
  const can = useCan();
  const { products, activeProduct, activeVariant } = state;
  const [gitStatus, setGitStatus] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [showNewProduct, setShowNewProduct] = useState(false);
  const [newProdId, setNewProdId] = useState('');
  const [newProdTitle, setNewProdTitle] = useState('');

  const refreshGitStatus = useCallback(() => {
    api.git.status().then(s => setGitStatus(s)).catch(() => {});
  }, []);

  useEffect(() => {
    refreshGitStatus();
    const id = setInterval(refreshGitStatus, 10_000);
    return () => clearInterval(id);
  }, [refreshGitStatus]);

  useEffect(() => {
    if (state._lastCommit) refreshGitStatus();
  }, [state._lastCommit, refreshGitStatus]);

  const handleProductChange = (e) => {
    const p = products.find(p => p.id === e.target.value) ?? null;
    dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: p });
  };

  const toggleTheme = () => {
    const next = state.theme === 'dark' ? 'light' : 'dark';
    dispatch({ type: 'SET_THEME', payload: next });
    document.documentElement.setAttribute('data-theme', next);
    document.documentElement.style.colorScheme = next;
    localStorage.setItem('reqtool:theme', next);   // persist
  };

  const handleCreateProduct = async () => {
    const id = newProdId.trim();
    const title = newProdTitle.trim() || id;
    if (!id) return;
    try {
      await api.products.create({ id, title, content: { description: '' } });
      const updated = await api.products.list();
      dispatch({ type: 'SET_PRODUCTS', payload: updated });
      const p = updated.find(p => p.id === id);
      if (p) dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: p });
      setShowNewProduct(false);
      setNewProdId(''); setNewProdTitle('');
      toast(`Product '${title}' created`, 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  // Shared remote (#348): pull, reload and validate, then push.
  const handleSync = async () => {
    setSyncing(true);
    try {
      const r = await api.git.sync();
      const problems = r.validation?.merge_errors ?? [];
      if (problems.length) {
        toast(`Synced, but the merge brought in ${problems.length} problem(s): `
          + [...new Set(problems.map(e => e.code))].join(', ') + '. Run Validate for details.', 'error', 8000);
      } else {
        toast(r.pushed ? 'Synced and pushed' : 'Up to date with the remote', 'success');
      }
      if (r.changed?.length) window.location.reload();
      else refreshGitStatus();
    } catch (err) {
      toast(err.message, 'error', 8000);
      refreshGitStatus();
    } finally {
      setSyncing(false);
    }
  };

  const variants = activeProduct?.variants ?? [];
  const stagedCount = (gitStatus?.staged ?? []).length;
  const unstagedCount = (gitStatus?.unstaged ?? []).length;

  return (
    <header className="header">
      <div className="header-left">
        <div className="header-brand">
          <span className="header-brand-icon">◈</span>
          <span className="header-brand-name">reqtool</span>
        </div>
        <div className="header-sep" />
        <select className="header-select" value={activeProduct?.id ?? ''} onChange={handleProductChange}>
          <option value="">— select product —</option>
          {products.map(p => <option key={p.id} value={p.id}>{p.title || p.id}</option>)}
        </select>
        {can('manage_modules') && <button
          className="btn btn-ghost"
          style={{ fontSize: 11, padding: '3px 8px', marginLeft: 2 }}
          onClick={() => setShowNewProduct(v => !v)}
          title="Create a new product"
        >+ Product</button>}
        {variants.length > 0 && (
          <select
            className="header-select header-select-sm"
            value={activeVariant ?? ''}
            onChange={e => dispatch({ type: 'SET_ACTIVE_VARIANT', payload: e.target.value || null })}
          >
            <option value="">All variants</option>
            {variants.map(v => <option key={v.id} value={v.id}>{v.title || v.id}</option>)}
          </select>
        )}
      </div>

      {showNewProduct && (
        <div className="header-new-product-popover">
          <input value={newProdId} onChange={e => setNewProdId(e.target.value)}
            placeholder="ID (e.g. sensor-v1)" autoFocus
            onKeyDown={e => e.key === 'Enter' && handleCreateProduct()} style={{ width: 140 }} />
          <input value={newProdTitle} onChange={e => setNewProdTitle(e.target.value)}
            placeholder="Title (optional)"
            onKeyDown={e => e.key === 'Enter' && handleCreateProduct()} style={{ width: 160 }} />
          <button className="btn btn-primary" style={{ fontSize: 11 }} onClick={handleCreateProduct}>Create</button>
          <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setShowNewProduct(false)}>✕</button>
        </div>
      )}

      <div className="header-centre">
        <div className="header-search" title="Filter items in the sidebar tree. For full-text search press Ctrl+K.">
          <span className="header-search-icon">⌕</span>
          <input
            type="search"
            placeholder="Filter tree…"
            value={state.searchQuery || ''}
            onChange={e => dispatch({ type: 'SET_SEARCH', payload: e.target.value })}
            className="header-search-input"
          />
          <span className="header-search-hint">Ctrl+K</span>
        </div>
      </div>

      <div className="header-right">
        {stagedCount > 0 && (
          <button className="header-staged-badge"
            title={`Click to commit:\n${(gitStatus?.staged || []).join('\n')}`}
            onClick={() => onGlobalCommit?.(gitStatus)}>
            ↑ {stagedCount} staged
          </button>
        )}
        {unstagedCount > 0 && (
          <span className="header-unstaged-badge">{unstagedCount} unstaged</span>
        )}
        {state.operatingMode && state.operatingMode !== 'local' && (
          <span className="header-unstaged-badge" title="Operating mode">{state.operatingMode}</span>
        )}
        {gitStatus?.sync?.remotes?.length > 0 && can('write') && (
          <button className="header-staged-badge" disabled={syncing} onClick={handleSync}
            title={`Sync with ${gitStatus.sync.upstream || gitStatus.sync.remotes[0]}: pull, then push your commits`}>
            {syncing ? 'Syncing…' : '⇅ Sync'}
            {gitStatus.sync.behind > 0 && ` ↓${gitStatus.sync.behind}`}
            {gitStatus.sync.ahead > 0 && ` ↑${gitStatus.sync.ahead}`}
          </button>
        )}
        {/* Primary actions */}
        <button className="btn btn-ghost header-action-btn" onClick={onValidate} title="Validate all requirements">✓ Validate</button>
        <button className="btn btn-ghost header-action-btn" onClick={onExport}   title="Export requirements">↓ Export</button>
        <button className="btn btn-ghost header-action-btn" onClick={onMetrics}  title="Metrics dashboard">⊕ Metrics</button>
        {/* Overflow menu */}
        <OverflowMenu groups={[
          { heading: 'View', items: [
            { label: '◔ Overview & release gate', action: onOverview },
            { label: '⇢ Roadmap', action: onRoadmap },
            { label: '◫ Views', action: () => dispatch({ type: 'TOGGLE_PANEL', key: '_showViews', value: true }) },
            { label: '⊞ Coverage', action: onCoverage },
            { label: '⊗ Traceability', action: onTraceability },
            { label: '⚖ Decisions & ADRs', action: onDecisions },
            { label: '⌕ Query & saved views', action: onQuery },
            { label: '✉ Inbox', action: onInbox },
          ] },
          { heading: 'Create and import', items: [
            { label: '≡ Bulk update', action: onBulk, needs: 'write' },
            { label: '⇪ Import CSV', action: onImport, needs: 'write' },
            { label: '⏱ Iterations & Gates', action: onIterations },
            { label: '⎇ Change sets', action: onChangeSets },
            { label: '✐ Diagram Canvas', action: onDiagram },
          ] },
          { heading: 'Quality', items: [
            { label: '✎ Writing check', action: () => dispatch({ type: 'TOGGLE_PANEL', key: '_showWritingCheck', value: true }) },
            { label: '⧉ Duplicate Detector', action: onDuplicateDetector },
          ] },
          { heading: 'Configure', items: [
            { label: '⬡ Workflows', action: () => dispatch({ type: 'TOGGLE_PANEL', key: '_showWorkflowEditor', value: true }) },
            { label: '⊙ Vocabularies', action: onVocabularies, needs: 'manage_config' },
            { label: '⊚ Custom fields', action: onCustomFields, needs: 'manage_config' },
            { label: '▤ Templates', action: onTemplates, needs: 'manage_config' },
            { label: '⚙ Automation Rules', action: onAutomation },
          ] },
          { heading: 'Admin', items: [
            { label: '▦ Modules', action: onModules },
            { label: '◎ Baselines', action: onBaselines },
            { label: '⇌ Webhooks', action: onWebhooks, needs: 'manage_webhooks' },
            { label: '⌂ Repository', action: onRepo, needs: 'manage_repo' },
          ] },
          { heading: 'Account', items: [
            { label: '⚿ Login / Server', action: onLogin },
          ] },
        ].map(g => ({ ...g, items: g.items.filter(item => !item.needs || can(item.needs)) })).filter(g => g.items.length)} />
        <button
          className="btn btn-ghost header-action-btn"
          onClick={toggleTheme}
          title={`Switch to ${state.theme === 'dark' ? 'light' : 'dark'} mode`}
          style={{ fontSize: 14, padding: '4px 8px' }}
        >{state.theme === 'dark' ? '☀' : '☾'}</button>
        <button
          className="btn btn-ghost header-action-btn"
          onClick={onHelp}
          title="Help, About & Templates (press ?)"
          style={{ fontWeight: 700, fontSize: 15, padding: '4px 10px', color: 'var(--text-secondary)' }}
        >?</button>
        <UserIdentityWidget onLogin={onLogin} />
      </div>
    </header>
  );
}
