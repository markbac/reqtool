/**
 * Header.jsx -- Top bar.
 * - Product/variant selector
 * - Live search (dispatches SET_SEARCH)
 * - Git status polling every 10s, refresh on commit
 * - Staged badge is clickable -> global commit modal
 * - Search (opens Ctrl+K), inbox, theme, help and account. Everything else is in the left-hand menu (#373).
 */

import { useEffect, useState, useCallback } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';
import './Header.css';

function UserIdentityWidget({ onLogin }) {
  const { state } = useApp();
  const currentUser = state.enums?._current_user || localStorage.getItem('reqtool:username') || 'user';

  return (
    <button
      className="btn btn-ghost"
      style={{ fontSize: 12, padding: '3px 7px', color: 'var(--text-muted)' }}
      onClick={onLogin}
      aria-label="Account"
      title="Account: log in or switch server"
    >👤 <span className="header-user-name">{currentUser}</span></button>
  );
}

export default function Header({ onGlobalCommit, onHelp, onLogin, onInbox, onSearch, onMenu }) {
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
        <button className="btn btn-ghost header-menu-btn" onClick={onMenu} aria-label="Menu" title="Menu">☰</button>
        <div className="header-brand">
          <span className="header-brand-icon">◈</span>
          <span className="header-brand-name">reqtool</span>
        </div>
        <div className="header-sep" />
        <select className="header-select" aria-label="Product" value={activeProduct?.id ?? ''} onChange={handleProductChange}>
          <option value="">Choose a product</option>
          {products.map(p => <option key={p.id} value={p.id}>{p.title || p.id}</option>)}
        </select>
        {can('manage_modules') && <button
          className="btn btn-ghost"
          style={{ fontSize: 12, padding: '3px 8px', marginLeft: 2 }}
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
          <button className="btn btn-primary" style={{ fontSize: 12 }} onClick={handleCreateProduct}>Create</button>
          <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => setShowNewProduct(false)}>✕</button>
        </div>
      )}

      <div className="header-centre">
        <button className="header-search" onClick={onSearch} aria-label="Search items, decisions and actions (Ctrl+K)"
          title="Search items, decisions and actions (Ctrl+K)">
          <span className="header-search-icon" aria-hidden="true">⌕</span>
          <span className="header-search-placeholder">Search items, decisions and actions</span>
          <span className="header-search-hint" aria-hidden="true">Ctrl+K</span>
        </button>
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
        <button className="btn btn-ghost header-action-btn" onClick={onInbox} aria-label="Inbox" title="Inbox">✉ Inbox</button>
        <button
          className="btn btn-ghost header-action-btn"
          onClick={toggleTheme}
          title={`Switch to ${state.theme === 'dark' ? 'light' : 'dark'} mode`}
          aria-label={`Switch to ${state.theme === 'dark' ? 'light' : 'dark'} mode`}
          style={{ fontSize: 14, padding: '4px 8px' }}
        >{state.theme === 'dark' ? '☀' : '☾'}</button>
        <button
          className="btn btn-ghost header-action-btn"
          onClick={onHelp}
          title="Help, About & Templates (press ?)" aria-label="Help"
          style={{ fontWeight: 700, fontSize: 15, padding: '4px 10px', color: 'var(--text-secondary)' }}
        >?</button>
        <UserIdentityWidget onLogin={onLogin} />
      </div>
    </header>
  );
}
