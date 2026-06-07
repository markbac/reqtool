/**
 * Header.jsx -- Top bar.
 * - Product/variant selector
 * - Live search (dispatches SET_SEARCH)
 * - Git status polling every 10s, refresh on commit
 * - Staged badge is clickable -> global commit modal
 * - Action buttons: Validate, Coverage, Bulk, Export
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import './Header.css';

function UserIdentityWidget() {
  const { state, dispatch } = useApp();
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState('');
  const currentUser = state.enums?._current_user || 'user';

  const save = () => {
    const name = val.trim() || 'user';
    localStorage.setItem('reqtool:username', name);
    dispatch({ type: 'SET_ENUMS', payload: { ...state.enums, _current_user: name } });
    setEditing(false);
  };

  if (editing) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <input
          autoFocus
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false); }}
          onBlur={save}
          placeholder="Your name"
          style={{ width: 110, height: 26, fontSize: 11 }}
        />
      </div>
    );
  }
  return (
    <button
      className="btn btn-ghost"
      style={{ fontSize: 11, padding: '3px 7px', color: 'var(--text-muted)' }}
      onClick={() => { setVal(currentUser === 'user' ? '' : currentUser); setEditing(true); }}
      title="Set your name (used for comments and approvals)"
    >👤 {currentUser}</button>
  );
}

function OverflowMenu({ items }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button className="btn btn-ghost header-action-btn" onClick={() => setOpen(v => !v)} title="More tools">⋯ More</button>
      {open && (
        <div className="overflow-menu">
          {items.map(item => (
            <button key={item.label} className="overflow-menu-item"
              onClick={() => { item.action?.(); setOpen(false); }}>
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Header({ onValidate, onExport, onCoverage, onBulk, onVocabularies,
                               onBaselines, onMetrics, onImport, onTraceability, onGlobalCommit,
                               onCustomFields, onWebhooks, onToggleSidebar, onHelp }) {
  const { state, dispatch, toast } = useApp();
  const { products, activeProduct, activeVariant } = state;
  const [gitStatus, setGitStatus] = useState(null);
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
        <button
          className="btn btn-ghost"
          style={{ fontSize: 11, padding: '3px 8px', marginLeft: 2 }}
          onClick={() => setShowNewProduct(v => !v)}
          title="Create a new product"
        >+ Product</button>
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
        <div className="header-search">
          <span className="header-search-icon">⌕</span>
          <input
            type="search"
            placeholder="Filter tree... (Ctrl+K for global search)"
            value={state.searchQuery || ''}
            onChange={e => dispatch({ type: 'SET_SEARCH', payload: e.target.value })}
            className="header-search-input"
          />
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
        {/* Primary actions */}
        <button className="btn btn-ghost header-action-btn" onClick={onValidate} title="Validate all requirements">✓ Validate</button>
        <button className="btn btn-ghost header-action-btn" onClick={onExport}   title="Export requirements">↓ Export</button>
        <button className="btn btn-ghost header-action-btn" onClick={onMetrics}  title="Metrics dashboard">⊕ Metrics</button>
        {/* Overflow menu */}
        <OverflowMenu items={[
          { label: '⊞ Coverage',     action: onCoverage },
          { label: '⊗ Traceability', action: onTraceability },
          { label: '◎ Baselines',    action: onBaselines },
          { label: '≡ Bulk update',  action: onBulk },
          { label: '⊙ Vocabularies', action: onVocabularies },
          { label: '⊚ Custom fields',action: onCustomFields },
          { label: '⇌ Webhooks',     action: onWebhooks },
          { label: '⬡ Workflow',     action: () => dispatch({ type: 'TOGGLE_PANEL', key: '_showWorkflow', value: true }) },
          { label: '↑ Import CSV',   action: onImport },
        ]} />
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
        <UserIdentityWidget />
      </div>
    </header>
  );
}
