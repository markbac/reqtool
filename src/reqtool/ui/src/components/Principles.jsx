/**
 * Principles.jsx -- principles grouped by area and category.
 *   PrinciplesPanel   the sidebar tree: Area > Category > Principle, with search, a status filter, add-to-category,
 *                     drag a principle onto another category to move it, and (administrators) default packs.
 *   PackDialog        choose default packs to add; ids already in the repository are never duplicated.
 *   PlacementFields   the area and category selectors used in the principle editor.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';
import './CommitModal.css';
import './Principles.css';

const UNPLACED = 'unplaced';
const EMPTY_CONTENT = { description: '', rationale: '', implications: '', exceptions: '' };

export const principlesChanged = () => window.dispatchEvent(new Event('reqtool:principles-changed'));

const statusOf = p => p.approval?.status ?? p.status ?? 'draft';

// ---------------------------------------------------------------------------
// Pack dialog
// ---------------------------------------------------------------------------
export function PackDialog({ onClose, onDone }) {
  const { toast } = useApp();
  const [packs, setPacks] = useState(null);
  const [chosen, setChosen] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.principles.packs().then(setPacks).catch(err => { toast(err.message, 'error'); onClose(); }); }, []);
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [busy, onClose]);

  const selected = Object.keys(chosen).filter(a => chosen[a]);
  const submit = async () => {
    setBusy(true);
    let added = 0;
    try {
      for (const area of selected) added += (await api.principles.addPack(area)).added;
      toast(added ? `Added ${added} principle${added === 1 ? '' : 's'}` : 'Nothing new to add', added ? 'success' : 'info');
      onDone?.();
      onClose();
    } catch (err) {
      toast(err.message, 'error');
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={() => !busy && onClose()}>
      <div className="modal principle-pack-dialog" role="dialog" aria-label="Add default principles" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Add default principles</span>
          <button className="modal-close btn-ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">
          <p className="principle-pack-hint">
            Each pack covers one area. Principles already in this repository are left alone, so adding a pack twice is safe.
          </p>
          {!packs && <div className="sidebar-loading"><div className="spinner" /></div>}
          {packs && packs.map(pack => {
            const full = pack.available === 0;
            return (
              <label key={pack.area} className={`principle-pack ${full ? 'principle-pack--full' : ''}`}>
                <input type="checkbox" disabled={full} checked={!!chosen[pack.area]}
                  aria-label={pack.label}
                  onChange={e => setChosen(c => ({ ...c, [pack.area]: e.target.checked }))} />
                <span className="principle-pack-body">
                  <span className="principle-pack-name">{pack.label}
                    <span className="principle-pack-count">{pack.installed} of {pack.count} in this repository</span>
                  </span>
                  <span className="principle-pack-desc">{pack.description}</span>
                  <span className="principle-pack-cats">
                    {pack.categories.filter(c => c.count).map(c => `${c.label} (${c.count})`).join(', ')}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={busy || selected.length === 0}>
            {busy ? <span className="spinner" /> : `Add ${selected.length || ''} pack${selected.length === 1 ? '' : 's'}`.replace('  ', ' ')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Editor selectors
// ---------------------------------------------------------------------------
export function PlacementFields({ area, category, onChange, disabled }) {
  const { toast } = useApp();
  const can = useCan();
  const [vocab, setVocab] = useState({});
  const [adding, setAdding] = useState(false);
  const [label, setLabel] = useState('');

  const load = useCallback(() => api.principles.vocabulary().then(v => setVocab(v.vocabulary || {})).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const areas = Object.entries(vocab);
  const known = vocab[area];
  const cats = Object.entries(known?.categories || {});

  const pickArea = (next) => {
    const first = Object.keys(vocab[next]?.categories || {});
    onChange({ area: next || null, category: next ? (first.includes('general') ? 'general' : first[0] || null) : null });
  };

  const addCategory = async () => {
    const slug = label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    if (!slug || !/^[a-z]/.test(slug)) { toast('Use a name that starts with a letter', 'error'); return; }
    try {
      const next = { ...vocab, [area]: { ...vocab[area], categories: { ...vocab[area].categories, [slug]: { label: label.trim() } } } };
      await api.principles.setVocabulary({ vocabulary: next });
      await load();
      onChange({ area, category: slug });
      setAdding(false); setLabel('');
      principlesChanged();
    } catch (err) { toast(err.message, 'error'); }
  };

  return (
    <>
      <div className="field-group">
        <label className="field-label" htmlFor="principle-area">Area</label>
        <select id="principle-area" value={area ?? ''} disabled={disabled} onChange={e => pickArea(e.target.value)}>
          <option value="">(none)</option>
          {area && !known && <option value={area}>{area} (not in the vocabulary)</option>}
          {areas.map(([id, spec]) => <option key={id} value={id}>{spec.label}</option>)}
        </select>
      </div>
      <div className="field-group">
        <label className="field-label" htmlFor="principle-category">Category</label>
        <select id="principle-category" value={category ?? ''} disabled={disabled || !area}
          onChange={e => onChange({ area, category: e.target.value || null })}>
          {category && !(known?.categories || {})[category] && <option value={category}>{category} (not in the vocabulary)</option>}
          {cats.map(([id, spec]) => <option key={id} value={id}>{spec.label}</option>)}
        </select>
        {can('manage_config') && area && known && !disabled && (
          adding ? (
            <span className="principle-add-category">
              <input aria-label="New category name" value={label} autoFocus placeholder="Category name"
                onChange={e => setLabel(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') addCategory(); if (e.key === 'Escape') setAdding(false); }} />
              <button className="btn btn-secondary" onClick={addCategory}>Add</button>
              <button className="btn btn-ghost" onClick={() => setAdding(false)}>Cancel</button>
            </span>
          ) : (
            <button className="btn btn-ghost principle-add-category-btn" onClick={() => setAdding(true)}>+ New category</button>
          )
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Sidebar tree
// ---------------------------------------------------------------------------
export function PrinciplesPanel() {
  const { state, dispatch, toast } = useApp();
  const can = useCan();
  const [items, setItems] = useState([]);
  const [tree, setTree] = useState({ areas: [], unplaced: 0 });
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState({});
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [showPacks, setShowPacks] = useState(false);
  const [hover, setHover] = useState(null);

  const load = useCallback(() => {
    return Promise.all([api.principles.list(), api.principles.areas()])
      .then(([list, areas]) => { setItems(list); setTree(areas); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    window.addEventListener('reqtool:principles-changed', load);
    return () => window.removeEventListener('reqtool:principles-changed', load);
  }, [load]);

  // The selected principle's area and category open by themselves.
  useEffect(() => {
    const sel = items.find(p => p.uid === state.selectedUid);
    if (sel) setOpen(o => ({ ...o, [`a:${sel.area || UNPLACED}`]: true, [`c:${sel.area || UNPLACED}/${sel.category || 'general'}`]: true }));
  }, [state.selectedUid, items]);

  const needle = search.trim().toLowerCase();
  const visible = useMemo(() => items.filter(p =>
    (!needle || `${p.id} ${p.title}`.toLowerCase().includes(needle)) && (!status || statusOf(p) === status)), [items, needle, status]);
  const statuses = useMemo(() => [...new Set(items.map(statusOf))].sort(), [items]);
  const forceOpen = !!(needle || status);

  const byPlace = useMemo(() => {
    const m = {};
    for (const p of visible) {
      const key = `${p.area || UNPLACED}/${p.category || 'general'}`;
      (m[key] = m[key] || []).push(p);
    }
    return m;
  }, [visible]);

  const toggle = (key) => setOpen(o => ({ ...o, [key]: !o[key] }));
  const isOpen = (key) => forceOpen || !!open[key];

  const create = async (area, category) => {
    try {
      const p = await api.principles.create({ title: 'New principle', content: EMPTY_CONTENT, ...(area ? { area, category } : {}) });
      dispatch({ type: 'SELECT', uid: p.uid, artefactType: 'principle' });
      await load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const move = async (uid, area, category, label) => {
    const p = items.find(i => i.uid === uid);
    if (!p || (p.area === area && p.category === category)) return;
    try {
      await api.principles.update(uid, { area, category });
      toast(`Moved ${p.id} to ${label}`, 'success');
      await load();
    } catch (err) { toast(err.message, 'error'); }
  };

  if (loading) return <div className="sidebar-loading"><div className="spinner" /></div>;

  const areas = [...tree.areas];
  if (tree.unplaced) areas.push({ id: UNPLACED, label: 'Unplaced', count: tree.unplaced, categories: [{ id: 'general', label: 'No area', count: tree.unplaced }] });

  return (
    <div className="list-panel principles-tree">
      <div className="list-panel-toolbar">
        <input className="list-search" placeholder="Search principles..." value={search} aria-label="Search principles"
          onChange={e => setSearch(e.target.value)} />
        {statuses.length > 1 && (
          <select className="principles-status" value={status} aria-label="Filter by status" onChange={e => setStatus(e.target.value)}>
            <option value="">All</option>
            {statuses.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        {can('write') && <button className="btn btn-ghost list-new-btn" onClick={() => create()}>+ New</button>}
        {can('manage_config') && <button className="btn btn-ghost list-new-btn" onClick={() => setShowPacks(true)}
          title="Add the default principles for one or more areas">+ Defaults</button>}
      </div>

      {!items.length && <div className="sidebar-empty">
        <div>No principles defined.</div>
        {can('manage_config') && <button className="btn btn-secondary" style={{ marginTop: 8, fontSize: 11 }} onClick={() => setShowPacks(true)}>Add default principles</button>}
      </div>}
      {items.length > 0 && visible.length === 0 && <div className="sidebar-empty">No principles match.</div>}

      {areas.map(area => {
        const cats = area.categories.map(c => ({ ...c, rows: byPlace[`${area.id}/${c.id}`] || [] })).filter(c => c.rows.length);
        const shown = cats.reduce((n, c) => n + c.rows.length, 0);
        if (!shown) return null;
        const aKey = `a:${area.id}`;
        return (
          <div key={area.id} className="principle-group" data-area={area.id}>
            <button className="principle-group-header principle-area-header" aria-expanded={isOpen(aKey)}
              onClick={() => toggle(aKey)}>
              <span className="principle-group-toggle">{isOpen(aKey) ? '▾' : '▸'}</span>
              <span className="principle-group-label">{area.label}</span>
              <span className="principle-group-count">{shown}</span>
            </button>
            {isOpen(aKey) && cats.map(cat => {
              const cKey = `c:${area.id}/${cat.id}`;
              const dropKey = `${area.id}/${cat.id}`;
              const droppable = can('write') && area.id !== UNPLACED;
              return (
                <div key={cat.id} className="principle-category" data-category={cat.id}>
                  <div className={`principle-category-header ${hover === dropKey ? 'principle-category-header--drop' : ''}`}
                    onDragOver={droppable ? (e) => { e.preventDefault(); setHover(dropKey); } : undefined}
                    onDragLeave={droppable ? () => setHover(null) : undefined}
                    onDrop={droppable ? (e) => {
                      e.preventDefault(); setHover(null);
                      move(e.dataTransfer.getData('text/plain'), area.id, cat.id, `${area.label} > ${cat.label}`);
                    } : undefined}>
                    <button className="principle-category-toggle" aria-expanded={isOpen(cKey)} onClick={() => toggle(cKey)}>
                      <span className="principle-group-toggle">{isOpen(cKey) ? '▾' : '▸'}</span>
                      <span className="principle-group-label">{cat.label}</span>
                      <span className="principle-group-count">{cat.rows.length}</span>
                    </button>
                    {droppable && (
                      <button className="principle-category-add" title={`New principle in ${area.label} > ${cat.label}`}
                        aria-label={`New principle in ${cat.label}`} onClick={() => create(area.id, cat.id)}>+</button>
                    )}
                  </div>
                  {isOpen(cKey) && cat.rows.map(p => (
                    <div key={p.uid} className={`list-item principle-row ${state.selectedUid === p.uid ? 'list-item--selected' : ''}`}
                      draggable={can('write')}
                      onDragStart={(e) => e.dataTransfer.setData('text/plain', p.uid)}
                      onClick={() => dispatch({ type: 'SELECT', uid: p.uid, artefactType: 'principle' })}>
                      <div className="list-item-header">
                        <span className="list-item-id mono">{p.id}</span>
                        <span className={`badge badge-${statusOf(p)}`}>{statusOf(p)}</span>
                      </div>
                      <div className="list-item-title">{p.title}</div>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        );
      })}

      {showPacks && <PackDialog onClose={() => setShowPacks(false)} onDone={() => { load(); principlesChanged(); }} />}
    </div>
  );
}
