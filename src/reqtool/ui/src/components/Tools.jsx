/**
 * Tools.jsx -- Panels and modals for power-user features:
 *   CoveragePanel, BulkUpdatePanel, GlobalCommitModal
 */

import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import './Tools.css';

// ---------------------------------------------------------------------------
// Coverage dashboard
// ---------------------------------------------------------------------------
export function CoveragePanel({ onClose }) {
  const { state } = useApp();
  const { activeProduct } = state;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const params = activeProduct ? { product: activeProduct.id } : {};
        const reqs = await api.requirements.list(params);
        const live = reqs.filter(r => !r.deleted);

        const total = live.length;
        const byStatus = {};
        const byPriority = {};
        let noAC = 0, noOwner = 0, noVerification = 0, noRationale = 0;

        for (const r of live) {
          byStatus[r.status || 'draft'] = (byStatus[r.status || 'draft'] || 0) + 1;
          byPriority[r.priority || 'medium'] = (byPriority[r.priority || 'medium'] || 0) + 1;
          if (!r.acceptance_criteria?.length) noAC++;
          if (!r.owner) noOwner++;
          if (r.verification?.status === 'not_started' || !r.verification?.status) noVerification++;
          if (!r.content?.rationale) noRationale++;
        }

        setData({ total, byStatus, byPriority, noAC, noOwner, noVerification, noRationale });
      } catch { setData(null); }
      finally { setLoading(false); }
    };
    load();
  }, [activeProduct]);

  const pct = (n) => data?.total ? Math.round((n / data.total) * 100) : 0;

  const STATUS_ORDER = ['approved', 'reviewed', 'draft', 'deprecated', 'deleted'];
  const STATUS_COLOURS = {
    approved: 'var(--status-approved)', reviewed: 'var(--status-reviewed)',
    draft: 'var(--status-draft)', deprecated: 'var(--status-deprecated)',
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel side-panel--wide" onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">Coverage</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        {loading && <div className="panel-body"><div className="panel-loading"><div className="spinner" /></div></div>}
        {!loading && !data && <div className="panel-body"><p style={{color:'var(--text-muted)'}}>No data.</p></div>}
        {!loading && data && (
          <div className="panel-body">
            <div className="cov-headline">{data.total} requirements</div>

            {/* Status breakdown */}
            <div className="cov-section-title">Status</div>
            <div className="cov-bar-stack">
              {STATUS_ORDER.filter(s => data.byStatus[s]).map(s => (
                <div
                  key={s}
                  className="cov-bar-seg"
                  style={{ width: pct(data.byStatus[s]) + '%', background: STATUS_COLOURS[s] || 'var(--border)' }}
                  title={`${s}: ${data.byStatus[s]}`}
                />
              ))}
            </div>
            <div className="cov-legend">
              {STATUS_ORDER.filter(s => data.byStatus[s]).map(s => (
                <span key={s} className="cov-legend-item">
                  <span className="cov-legend-dot" style={{ background: STATUS_COLOURS[s] || 'var(--border)' }} />
                  {s} <span className="text-muted">({data.byStatus[s]})</span>
                </span>
              ))}
            </div>

            {/* Quality gaps */}
            <div className="cov-section-title" style={{ marginTop: 16 }}>Quality gaps</div>
            {[
              { label: 'No acceptance criteria', n: data.noAC, warn: true },
              { label: 'No owner assigned',       n: data.noOwner, warn: true },
              { label: 'Verification not started',n: data.noVerification, warn: data.noVerification > 0 },
              { label: 'No rationale',            n: data.noRationale, warn: false },
            ].map(({ label, n, warn }) => (
              <div key={label} className="cov-gap-row">
                <span className="cov-gap-label">{label}</span>
                <div className="cov-gap-bar-wrap">
                  <div
                    className="cov-gap-bar"
                    style={{ width: pct(n) + '%', background: warn && n > 0 ? 'var(--accent-orange)' : 'var(--border)' }}
                  />
                </div>
                <span className={`cov-gap-count ${warn && n > 0 ? 'text-warn' : 'text-muted'}`}>
                  {n} <span className="text-muted" style={{ fontSize: 10 }}>({pct(n)}%)</span>
                </span>
              </div>
            ))}

            {/* Priority breakdown */}
            <div className="cov-section-title" style={{ marginTop: 16 }}>Priority</div>
            {['critical','high','medium','low'].filter(p => data.byPriority[p]).map(p => (
              <div key={p} className="cov-gap-row">
                <span className="cov-gap-label">{p}</span>
                <div className="cov-gap-bar-wrap">
                  <div className="cov-gap-bar" style={{ width: pct(data.byPriority[p]) + '%', background: 'var(--accent-blue)' }} />
                </div>
                <span className="cov-gap-count text-muted">{data.byPriority[p]}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bulk update panel
// ---------------------------------------------------------------------------
export function BulkUpdatePanel({ onClose, onDone }) {
  const { state, toast } = useApp();
  const { activeProduct, enums } = state;
  const [reqs, setReqs] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [fields, setFields] = useState({ status: '', priority: '', owner: '' });
  const [filterStatus, setFilterStatus] = useState('');

  useEffect(() => {
    setLoading(true);
    const params = activeProduct ? { product: activeProduct.id } : {};
    api.requirements.list(params)
      .then(data => setReqs(data.filter(r => !r.deleted)))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeProduct]);

  const filtered = filterStatus ? reqs.filter(r => r.status === filterStatus) : reqs;
  const allSelected = filtered.length > 0 && filtered.every(r => selected.has(r.uid));

  const toggle = (uid) => setSelected(s => { const n = new Set(s); n.has(uid) ? n.delete(uid) : n.add(uid); return n; });
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(filtered.map(r => r.uid)));

  const handleApply = async () => {
    const uids = [...selected];
    if (!uids.length) { toast('No requirements selected', 'info'); return; }
    const patch = {};
    if (fields.status)   patch.status   = fields.status;
    if (fields.priority) patch.priority = fields.priority;
    if (fields.owner)    patch.owner    = fields.owner;
    if (!Object.keys(patch).length) { toast('No fields to update', 'info'); return; }

    setBusy(true);
    try {
      const res = await api.requirements.bulk({ uids, fields: patch, summary: 'Bulk update' });
      toast(`Updated ${res.count} requirement(s)`, 'success');
      onDone?.();
      onClose();
    } catch (err) { toast(err.message, 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel side-panel--wide" onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">Bulk Update <span className="text-muted" style={{fontSize:11}}>({selected.size} selected)</span></span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="panel-body" style={{ gap: 8 }}>

          {/* Fields to set */}
          <div className="bulk-fields">
            <div className="field-group" style={{ flex: 1 }}>
              <label className="field-label">Set Status</label>
              <select value={fields.status} onChange={e => setFields(f => ({ ...f, status: e.target.value }))}>
                <option value="">— no change —</option>
                {(enums?.status || []).map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="field-group" style={{ flex: 1 }}>
              <label className="field-label">Set Priority</label>
              <select value={fields.priority} onChange={e => setFields(f => ({ ...f, priority: e.target.value }))}>
                <option value="">— no change —</option>
                {(enums?.priority || []).map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="field-group" style={{ flex: 1 }}>
              <label className="field-label">Set Owner</label>
              <input value={fields.owner} onChange={e => setFields(f => ({ ...f, owner: e.target.value }))} placeholder="username or email" />
            </div>
          </div>

          {/* Filter bar */}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Filter:</span>
            {['', ...(enums?.status || [])].map(s => (
              <button
                key={s}
                className={`tbds-filter-btn ${filterStatus === s ? 'active' : ''}`}
                onClick={() => setFilterStatus(s)}
              >{s || 'all'}</button>
            ))}
          </div>

          {/* Requirement list */}
          {loading
            ? <div className="panel-loading"><div className="spinner" /></div>
            : (
              <div className="bulk-list">
                <div className="bulk-list-header">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} style={{ width: 'auto' }} />
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Select all ({filtered.length})</span>
                </div>
                {filtered.map(r => (
                  <label key={r.uid} className={`bulk-row ${selected.has(r.uid) ? 'bulk-row--selected' : ''}`}>
                    <input type="checkbox" checked={selected.has(r.uid)} onChange={() => toggle(r.uid)} style={{ width: 'auto', flexShrink: 0 }} />
                    <span className="mono" style={{ fontSize: 11, width: 110, flexShrink: 0 }}>{r.id}</span>
                    <span style={{ fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.title}</span>
                    <span className={`badge badge-${r.status}`} style={{ flexShrink: 0 }}>{r.status}</span>
                  </label>
                ))}
              </div>
            )
          }

          <button
            className="btn btn-primary"
            style={{ width: '100%' }}
            onClick={handleApply}
            disabled={busy || !selected.size}
          >
            {busy ? <span className="spinner" /> : `Apply to ${selected.size} requirement(s)`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Global commit modal (commits all staged files)
// ---------------------------------------------------------------------------
export function GlobalCommitModal({ onClose, onDone, staged = [] }) {
  const { toast, dispatch } = useApp();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const handleCommit = async () => {
    if (!message.trim()) { toast('Commit message required', 'info'); return; }
    setBusy(true);
    try {
      const result = await api.git.commit({ message: message.trim(), uids: [] });
      toast(`Committed: ${result.commit_sha?.slice(0, 7)}`, 'success');
      dispatch({ type: 'COMMITTED' });
      onDone?.();
      onClose();
    } catch (err) { toast(err.message, 'error'); }
    finally { setBusy(false); }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()} style={{ width: 460 }}>
        <div className="modal-header">
          <span className="modal-title">Commit staged files</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          {staged.length > 0 && (
            <div className="staged-file-list">
              {staged.map(f => <div key={f} className="staged-file mono">{f}</div>)}
            </div>
          )}
          <div className="field-group">
            <label className="field-label">Commit message</label>
            <input
              value={message}
              onChange={e => setMessage(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCommit()}
              placeholder="feat(reqs): ..."
              autoFocus
            />
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleCommit} disabled={busy || !message.trim()}>
            {busy ? <span className="spinner" /> : 'Commit'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Vocabularies panel -- manage controlled lists in enums.yaml
// ---------------------------------------------------------------------------
export function VocabulariesPanel({ onClose }) {
  const { state, dispatch, toast } = useApp();
  const [enums, setEnums] = useState(null);
  const [saving, setSaving] = useState(false);
  const [activeVocab, setActiveVocab] = useState('tags');

  const VOCAB_SECTIONS = [
    { key: 'tags',        label: 'Tags',                hint: 'Labels applied to requirements, principles and TBDs. Use to group by theme, regulatory driver, etc.' },
    { key: 'team',        label: 'Teams',               hint: 'Used in Allocated To. Represents engineering teams or workstreams responsible for delivering requirements.' },
    { key: 'owner',       label: 'People',              hint: 'People list used in Owner, Approved By, and Reviewers fields. Use short identifiers (e.g. jane.smith or Systems Lead).' },
    { key: 'domain',      label: 'Domains',             hint: 'Requirement domain / area. Drives left-border colour coding in the tree and domain-split Markdown exports.' },
    { key: 'discipline',  label: 'Disciplines',         hint: 'Engineering discipline (FW, HW, Sys, Mfg, etc.). Used to allocate derived requirements to delivery teams.' },
    { key: 'component',   label: 'Components',          hint: 'Physical or logical component. Used to allocate requirements to system elements.' },
    { key: 'feature',     label: 'Features',            hint: 'Feature or workstream grouping. Useful for sprint/release planning views.' },
    { key: 'safety_class',label: 'Safety Classifications', hint: 'Safety integrity levels (SIL-1..4, ASIL-A..D, Cat-1..3, etc.). Used on safety-related requirements.' },
    { key: 'nfr_keys',    label: 'NFR Keys',            hint: 'Registered non-functional requirement metric names (e.g. latency_ms, accuracy_degc). Unregistered keys warn on validation.' },
  ];

  useEffect(() => {
    api.enums.repo().then(data => setEnums(data)).catch(() => toast('Could not load enums', 'error'));
  }, []);

  const getList = (key) => (enums?.[key] ?? []);

  const setList = (key, list) => setEnums(e => ({ ...e, [key]: list }));

  const addItem = (key, val) => {
    const v = val.trim();
    if (!v) return;
    const existing = getList(key);
    if (existing.includes(v)) { toast(`'${v}' already exists`, 'info'); return; }
    setList(key, [...existing, v]);
  };

  const removeItem = (key, val) => setList(key, getList(key).filter(i => i !== val));

  const renameItem = (key, oldVal, newVal) => {
    const v = newVal.trim();
    if (!v || v === oldVal) return;
    const existing = getList(key);
    if (existing.includes(v)) { toast(`'${v}' already exists`, 'info'); return; }
    setList(key, existing.map(i => i === oldVal ? v : i));
  };

  const handleSave = async () => {
    if (!enums) return;
    setSaving(true);
    try {
      const merged = await api.enums.updateRepo(enums);
      // Refresh app-wide enums
      const all = await api.enums.all();
      dispatch({ type: 'SET_ENUMS', payload: all });
      toast('Vocabularies saved', 'success');
    } catch (err) { toast(err.message, 'error'); }
    finally { setSaving(false); }
  };

  const current = VOCAB_SECTIONS.find(s => s.key === activeVocab);

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel side-panel--wide" onClick={e => e.stopPropagation()} style={{ width: 580 }}>
        <div className="side-panel-header">
          <span className="side-panel-title">Vocabularies</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving || !enums}>
              {saving ? <span className="spinner" /> : 'Save'}
            </button>
            <button className="btn btn-ghost" onClick={onClose}>✕</button>
          </div>
        </div>

        {!enums
          ? <div className="panel-body"><div className="panel-loading"><div className="spinner" /></div></div>
          : (
            <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
              {/* Left nav */}
              <div className="vocab-nav">
                {VOCAB_SECTIONS.map(s => (
                  <button
                    key={s.key}
                    className={`vocab-nav-item ${activeVocab === s.key ? 'active' : ''}`}
                    onClick={() => setActiveVocab(s.key)}
                  >
                    <span>{s.label}</span>
                    <span className="vocab-count">{getList(s.key).length}</span>
                  </button>
                ))}
              </div>

              {/* Right editor */}
              <div className="vocab-editor">
                <div className="vocab-editor-header">
                  <span className="vocab-editor-title">{current?.label}</span>
                  <span className="vocab-editor-hint">{current?.hint}</span>
                </div>
                <VocabItemList
                  items={getList(activeVocab)}
                  onAdd={val => addItem(activeVocab, val)}
                  onRemove={val => removeItem(activeVocab, val)}
                  onRename={(old, nw) => renameItem(activeVocab, old, nw)}
                  vocabKey={activeVocab}
                />
              </div>
            </div>
          )
        }
      </div>
    </div>
  );
}

function VocabItemList({ items, onAdd, onRemove, onRename, vocabKey }) {
  const [newVal, setNewVal] = useState('');
  const [editing, setEditing] = useState(null); // index being edited
  const [editVal, setEditVal] = useState('');

  const commitAdd = () => {
    const v = newVal.trim();
    if (!v) return;
    onAdd(v);
    setNewVal('');
  };

  const commitRename = (old) => {
    onRename(old, editVal);
    setEditing(null);
  };

  return (
    <div className="vocab-list">
      {items.length === 0 && (
        <div className="vocab-empty">No entries yet. Add below.</div>
      )}
      {items.map((item, idx) => (
        <div key={item} className="vocab-item">
          {editing === idx ? (
            <input
              autoFocus
              value={editVal}
              onChange={e => setEditVal(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') commitRename(item);
                if (e.key === 'Escape') setEditing(null);
              }}
              onBlur={() => commitRename(item)}
              className="vocab-item-input"
            />
          ) : (
            <span
              className="vocab-item-label"
              onDoubleClick={() => { setEditing(idx); setEditVal(item); }}
              title="Double-click to rename"
            >{item}</span>
          )}
          <div className="vocab-item-actions">
            <button
              className="btn btn-ghost vocab-item-btn"
              title="Rename"
              onClick={() => { setEditing(idx); setEditVal(item); }}
            >✎</button>
            <button
              className="btn btn-ghost vocab-item-btn"
              style={{ color: 'var(--accent-red)' }}
              title="Remove"
              onClick={() => onRemove(item)}
            >✕</button>
          </div>
        </div>
      ))}

      <div className="vocab-add">
        <input
          value={newVal}
          onChange={e => setNewVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && commitAdd()}
          placeholder={`Add ${vocabKey === 'nfr_keys' ? 'NFR key (e.g. latency_ms)' : 'new entry'}...`}
          className="vocab-add-input"
        />
        <button className="btn btn-primary" onClick={commitAdd} disabled={!newVal.trim()}>
          + Add
        </button>
      </div>
    </div>
  );
}
