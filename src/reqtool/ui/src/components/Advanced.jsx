/**
 * Advanced.jsx
 * New panels: Baselines, Metrics, Import, Traceability, CmdPalette, Workflow, Templates
 */

import { useState, useEffect, useRef } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import './Advanced.css';

// ---------------------------------------------------------------------------
// Shared panel shell
// ---------------------------------------------------------------------------
function Panel({ title, onClose, width = 520, children }) {
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" style={{ width }} onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">{title}</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="panel-body">
          {children}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Command Palette (Ctrl+K global search)
// ---------------------------------------------------------------------------
export function CmdPalette({ onClose, onSelect }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const t = setTimeout(() => {
      api.search(query, 30).then(r => { setResults(r); setSelected(0); }).catch(() => {});
    }, 150);
    return () => clearTimeout(t);
  }, [query]);

  const handleKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, results.length - 1)); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
    if (e.key === 'Enter' && results[selected]) {
      onSelect(results[selected].uid, results[selected].type);
    }
    if (e.key === 'Escape') onClose();
  };

  const TYPE_LABELS = { requirement: 'REQ', principle: 'P', tbd: 'TBD' };

  return (
    <div className="cmdpalette-overlay" onClick={onClose}>
      <div className="cmdpalette" onClick={e => e.stopPropagation()}>
        <div className="cmdpalette-search">
          <span className="cmdpalette-icon">⌕</span>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Search requirements, principles, TBDs..."
            className="cmdpalette-input"
          />
          <span className="cmdpalette-hint">↑↓ navigate · Enter select · Esc close</span>
        </div>
        {results.length > 0 && (
          <div className="cmdpalette-results">
            {results.map((r, i) => (
              <div
                key={r.uid}
                className={`cmdpalette-result ${i === selected ? 'cmdpalette-result--selected' : ''}`}
                onMouseEnter={() => setSelected(i)}
                onClick={() => onSelect(r.uid, r.type)}
              >
                <span className="cmdpalette-type-badge">{TYPE_LABELS[r.type] || r.type}</span>
                <span className="cmdpalette-id mono">{r.id}</span>
                <span className="cmdpalette-title">{r.title}</span>
              </div>
            ))}
          </div>
        )}
        {query.trim() && results.length === 0 && (
          <div className="cmdpalette-empty">No results for "{query}"</div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Baselines panel
// ---------------------------------------------------------------------------
export function BaselinesPanel({ onClose }) {
  const { toast } = useApp();
  const [baselines, setBaselines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newMsg, setNewMsg] = useState('');
  const [diff, setDiff] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api.baselines.list().then(setBaselines).catch(() => setBaselines([])).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await api.baselines.create({ name: newName.trim(), message: newMsg.trim() || undefined });
      toast(`Baseline '${newName}' created`, 'success');
      setCreating(false); setNewName(''); setNewMsg('');
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleDiff = async (name) => {
    setDiffLoading(true); setDiff(null);
    try {
      const d = await api.baselines.diff(name);
      setDiff(d);
    } catch (err) { toast(err.message, 'error'); }
    finally { setDiffLoading(false); }
  };

  return (
    <Panel title="Baselines" onClose={onClose} width={540}>
      <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }}
        onClick={() => setCreating(v => !v)}>
        + Create baseline
      </button>

      {creating && (
        <div className="baseline-create-form">
          <input value={newName} onChange={e => setNewName(e.target.value)}
            placeholder="Name (e.g. v1.0-rc1)" onKeyDown={e => e.key === 'Enter' && handleCreate()} />
          <input value={newMsg} onChange={e => setNewMsg(e.target.value)}
            placeholder="Description (optional)" />
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreate} disabled={!newName.trim()}>Create</button>
            <button className="btn btn-secondary" onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </div>
      )}

      {loading && <div className="panel-loading"><div className="spinner" /></div>}
      {!loading && baselines.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          No baselines yet. Create one to snapshot the current requirements state.
        </div>
      )}

      {baselines.map(b => (
        <div key={b.name} className="baseline-item">
          <div className="baseline-item-header">
            <span className="baseline-name mono">{b.name.replace('baseline/', '')}</span>
            <span className="baseline-date text-muted">{b.date?.slice(0, 10)}</span>
            <button className="btn btn-ghost" style={{ fontSize: 11 }}
              onClick={() => handleDiff(b.name.replace('baseline/', ''))}>
              Diff vs now
            </button>
          </div>
          {b.message && <div className="baseline-msg text-secondary">{b.message}</div>}
          <div className="baseline-sha mono text-muted">{b.sha}</div>
        </div>
      ))}

      {diffLoading && <div className="panel-loading"><div className="spinner" /></div>}
      {diff && (
        <div className="baseline-diff">
          <div className="baseline-diff-title">Changes since baseline/{diff.baseline?.replace('baseline/', '')}</div>
          {diff.added?.length > 0 && (
            <div className="diff-group diff-group--added">
              <div className="diff-group-header">+ {diff.added.length} added</div>
              {diff.added.map(r => <div key={r.id} className="diff-item mono">{r.id}</div>)}
            </div>
          )}
          {diff.removed?.length > 0 && (
            <div className="diff-group diff-group--removed">
              <div className="diff-group-header">− {diff.removed.length} removed</div>
              {diff.removed.map(r => <div key={r.path} className="diff-item mono">{r.id || r.path}</div>)}
            </div>
          )}
          {diff.changed?.length > 0 && (
            <div className="diff-group diff-group--changed">
              <div className="diff-group-header">~ {diff.changed.length} changed</div>
              {diff.changed.map(r => (
                <div key={r.id} className="diff-item">
                  <span className="mono">{r.id}</span>
                  <span className="text-muted" style={{ fontSize: 10, marginLeft: 8 }}>v{r.current_version}</span>
                </div>
              ))}
            </div>
          )}
          {!diff.added?.length && !diff.removed?.length && !diff.changed?.length && (
            <div style={{ color: 'var(--status-approved)', fontSize: 12 }}>✓ No changes since this baseline</div>
          )}
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Metrics dashboard
// ---------------------------------------------------------------------------
export function MetricsPanel({ onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.metrics.get().then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  const pct = (n, total) => total ? Math.round(n / total * 100) : 0;

  const STATUS_COLOURS = {
    approved: 'var(--status-approved)', in_review: 'var(--accent-orange)',
    reviewed: 'var(--accent-blue)', draft: 'var(--text-muted)',
    deprecated: 'var(--accent-red)',
  };

  return (
    <Panel title="Metrics" onClose={onClose} width={540}>
      {loading && <div className="panel-loading"><div className="spinner" /></div>}
      {!loading && !data && <div className="text-muted">Could not load metrics.</div>}
      {data && (<>
        {/* Headline numbers */}
        <div className="metrics-headlines">
          {[
            { label: 'Requirements', value: data.totals.requirements },
            { label: 'Principles',   value: data.totals.principles },
            { label: 'TBDs',         value: data.totals.tbds, warn: data.totals.open_tbds > 0 },
            { label: 'Open TBDs',    value: data.totals.open_tbds, warn: data.totals.open_tbds > 0 },
          ].map(({ label, value, warn }) => (
            <div key={label} className="metrics-headline-card">
              <div className={`metrics-headline-value ${warn ? 'metrics-warn' : ''}`}>{value}</div>
              <div className="metrics-headline-label">{label}</div>
            </div>
          ))}
        </div>

        {/* Approval funnel */}
        <div className="metrics-section-title">Approval funnel</div>
        <div className="metrics-funnel">
          {Object.entries(data.status).sort((a,b) => b[1]-a[1]).map(([s, n]) => (
            <div key={s} className="metrics-bar-row">
              <span className="metrics-bar-label">{s}</span>
              <div className="metrics-bar-track">
                <div className="metrics-bar-fill"
                  style={{ width: pct(n, data.totals.requirements) + '%', background: STATUS_COLOURS[s] || 'var(--border)' }} />
              </div>
              <span className="metrics-bar-count">{n}</span>
            </div>
          ))}
        </div>
        <div className="metrics-approval-rate">
          Approval rate: <strong>{data.approval_funnel.approval_rate_pct}%</strong>
        </div>

        {/* Quality gaps */}
        <div className="metrics-section-title">Quality gaps</div>
        {Object.entries(data.quality_gaps).map(([key, n]) => (
          <div key={key} className="metrics-bar-row">
            <span className="metrics-bar-label">{key.replace(/_/g,' ')}</span>
            <div className="metrics-bar-track">
              <div className="metrics-bar-fill"
                style={{ width: pct(n, data.totals.requirements) + '%', background: n > 0 ? 'var(--accent-orange)' : 'var(--border)' }} />
            </div>
            <span className="metrics-bar-count" style={{ color: n > 0 ? 'var(--accent-orange)' : 'var(--text-muted)' }}>{n}</span>
          </div>
        ))}

        {/* Velocity */}
        <div className="metrics-section-title">Activity</div>
        <div className="metrics-velocity">
          <strong>{data.velocity.changes_last_30d}</strong> requirement changes in the last 30 days
        </div>

        {/* Domain breakdown */}
        <div className="metrics-section-title">By domain</div>
        <div className="metrics-domain-grid">
          {Object.entries(data.domain).sort((a,b) => b[1]-a[1]).map(([d, n]) => (
            <div key={d} className="metrics-domain-chip">
              <span>{d}</span><span className="metrics-domain-count">{n}</span>
            </div>
          ))}
        </div>
      </>)}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// CSV Import panel
// ---------------------------------------------------------------------------
export function ImportPanel({ onClose, onDone }) {
  const { toast } = useApp();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    const reader = new FileReader();
    reader.onload = (ev) => {
      setPreview(ev.target.result?.slice(0, 1000) + (ev.target.result?.length > 1000 ? '...' : ''));
    };
    reader.readAsText(f);
  };

  const handleImport = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const text = await file.text();
      const res = await api.importCsv(text);
      setResult(res);
      toast(`Imported ${res.imported} requirements`, 'success');
      if (res.imported > 0) onDone?.();
    } catch (err) { toast(err.message, 'error'); }
    finally { setBusy(false); }
  };

  return (
    <Panel title="Import from CSV" onClose={onClose} width={540}>
      <div className="import-hint">
        Imports requirements from a CSV file. Column mapping is flexible:
        <code> id, title, status, priority, req_type, domain, owner, discipline,
        parentId, content.description, content.rationale, tags (semicolon-separated),
        allocated_to (semicolon-separated), verification_method, safety_related</code>.
        Only <strong>title</strong> is required.
      </div>

      <div className="field-group">
        <label className="field-label">CSV file</label>
        <input type="file" accept=".csv,text/csv" onChange={handleFile}
          style={{ padding: 4, cursor: 'pointer' }} />
      </div>

      {preview && (
        <div className="import-preview">
          <div className="import-preview-label">Preview (first 1000 chars)</div>
          <pre className="import-preview-text">{preview}</pre>
        </div>
      )}

      {result && (
        <div className="import-result">
          <div className="import-result-ok">✓ Imported {result.imported} requirements</div>
          {result.errors?.length > 0 && (
            <div className="import-result-errors">
              {result.errors.map((e, i) => (
                <div key={i} className="import-error-row">Row {e.row}: {e.error}</div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-primary" onClick={handleImport} disabled={!file || busy}>
          {busy ? <span className="spinner" /> : 'Import'}
        </button>
        <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Traceability matrix panel
// ---------------------------------------------------------------------------
export function TraceabilityPanel({ onClose }) {
  const { state } = useApp();
  const { activeProduct } = state;
  const [matrix, setMatrix] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeProduct) { setLoading(false); return; }
    api.products.matrix(activeProduct.id)
      .then(setMatrix)
      .catch(() => setMatrix(null))
      .finally(() => setLoading(false));
  }, [activeProduct]);

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="wide-panel" onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">Traceability Matrix</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="wide-panel-body">
          {!activeProduct && <div className="text-muted">Select a product first.</div>}
          {loading && <div className="panel-loading"><div className="spinner" /></div>}
          {!loading && matrix && (
            <div className="trace-wrap">
              <table className="trace-table">
                <thead>
                  <tr>
                    <th className="trace-th trace-th--id">ID</th>
                    <th className="trace-th trace-th--title">Title</th>
                    {matrix.teams.map(t => (
                      <th key={t} className="trace-th trace-th--team">{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.requirements.map(r => (
                    <tr key={r.uid} className="trace-row">
                      <td className="trace-td trace-td--id mono">{r.id}</td>
                      <td className="trace-td trace-td--title">{r.title}</td>
                      {matrix.teams.map(t => (
                        <td key={t} className="trace-td trace-td--cell">
                          {r.teams[t] ? <span className="trace-check">✓</span> : ''}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!loading && matrix && matrix.teams.length === 0 && (
            <div className="text-muted">
              No teams allocated. Use Allocated To on requirements to populate this matrix.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Workflow configuration panel
// ---------------------------------------------------------------------------
export function WorkflowPanel({ onClose }) {
  const { state, dispatch, toast } = useApp();
  const [wf, setWf] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.workflow.get().then(setWf).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.workflow.update(wf);
      dispatch({ type: 'SET_WORKFLOW', payload: updated });
      toast('Workflow saved', 'success');
    } catch (err) { toast(err.message, 'error'); }
    finally { setSaving(false); }
  };

  if (!wf) return <Panel title="Workflow" onClose={onClose}><div className="panel-loading"><div className="spinner" /></div></Panel>;

  return (
    <Panel title="Workflow configuration" onClose={onClose} width={500}>
      <div className="wf-hint">
        States and transitions define the lifecycle of requirements. The <strong>approved</strong> state
        triggers acceptance criteria validation. Edit <code>.reqtool/defaults/workflow.yaml</code> to
        change the defaults for new repositories.
      </div>

      <div className="metrics-section-title">States</div>
      {wf.states?.map((s, i) => (
        <div key={s.id} className="wf-state-row">
          <span className="wf-dot" style={{ background: s.colour }} />
          <span className="wf-state-id mono">{s.id}</span>
          <span className="wf-state-label">{s.label}</span>
          {s.terminal && <span className="badge" style={{ fontSize: 9 }}>terminal</span>}
          <span className="text-muted" style={{ fontSize: 11, marginLeft: 4 }}>→ {(wf.transitions?.[s.id] || []).join(', ') || '—'}</span>
        </div>
      ))}

      <div className="metrics-section-title" style={{ marginTop: 12 }}>Initial state</div>
      <select value={wf.initial} onChange={e => setWf(w => ({ ...w, initial: e.target.value }))}
        style={{ width: 200 }}>
        {wf.states?.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
      </select>

      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? <span className="spinner" /> : 'Save'}
        </button>
        <button className="btn btn-secondary" onClick={onClose}>Close</button>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Templates panel
// ---------------------------------------------------------------------------
export function TemplatesPanel({ onClose }) {
  const { state, dispatch, toast } = useApp();
  const { templates } = state;
  const [selected, setSelected] = useState(null);

  const applyTemplate = (template) => {
    // Dispatch a special action that the Editor can listen for
    dispatch({ type: 'APPLY_TEMPLATE', payload: template });
    toast(`Template '${template.label}' ready -- create a new requirement to apply it`, 'info', 4000);
    onClose();
  };

  return (
    <Panel title="Requirement templates" onClose={onClose} width={500}>
      <div className="import-hint">
        Templates pre-fill fields when creating a new requirement. Edit
        <code>.reqtool/templates.yaml</code> to customise them.
      </div>
      {templates.length === 0 && <div className="text-muted">No templates defined.</div>}
      {templates.map(t => (
        <div
          key={t.id}
          className={`template-item ${selected === t.id ? 'template-item--selected' : ''}`}
          onClick={() => setSelected(t.id === selected ? null : t.id)}
        >
          <div className="template-item-header">
            <span className="template-label">{t.label}</span>
            <button className="btn btn-primary" style={{ fontSize: 11, padding: '3px 10px' }}
              onClick={e => { e.stopPropagation(); applyTemplate(t); }}>
              Use
            </button>
          </div>
          {t.description && <div className="template-desc">{t.description}</div>}
          {selected === t.id && t.fields && (
            <div className="template-fields">
              {Object.entries(t.fields).filter(([k]) => k !== 'content').map(([k, v]) => (
                <div key={k} className="template-field-row">
                  <span className="mono text-secondary" style={{ fontSize: 11 }}>{k}</span>
                  <span style={{ fontSize: 11 }}>{Array.isArray(v) ? v.join(', ') : String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Attachment panel (used inside Editor as a section)
// ---------------------------------------------------------------------------
export function AttachmentsSection({ uid }) {
  const { toast } = useApp();
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const load = () => {
    api.attachments.list(uid).then(setAttachments).catch(() => {});
  };
  useEffect(() => { load(); }, [uid]);

  const handleFiles = async (files) => {
    setUploading(true);
    for (const file of files) {
      try {
        await api.attachments.upload(uid, file.name, file);
        toast(`Uploaded: ${file.name}`, 'success', 2000);
      } catch (err) { toast(`Upload failed: ${err.message}`, 'error'); }
    }
    setUploading(false);
    load();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    handleFiles([...e.dataTransfer.files]);
  };

  const handleDelete = async (filename) => {
    if (!confirm(`Delete attachment '${filename}'?`)) return;
    try {
      await api.attachments.delete(uid, filename);
      toast('Deleted', 'info', 1500);
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const fmtSize = (bytes) => bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes/1024).toFixed(1)} KB` : `${(bytes/1048576).toFixed(1)} MB`;

  return (
    <div className="attachments-section">
      {attachments.length > 0 && (
        <div className="attachment-list">
          {attachments.map(a => (
            <div key={a.filename} className="attachment-item">
              <span className="attachment-icon">{getFileIcon(a.filename)}</span>
              <a
                href={api.attachments.download(uid, a.filename)}
                target="_blank" rel="noopener noreferrer"
                className="attachment-name"
              >{a.filename}</a>
              <span className="attachment-meta">{fmtSize(a.size_bytes)}</span>
              <span className="attachment-meta">{a.added_by}</span>
              {a.description && <span className="attachment-meta text-muted">{a.description}</span>}
              <button className="string-list-remove" onClick={() => handleDelete(a.filename)} title="Delete attachment">✕</button>
            </div>
          ))}
        </div>
      )}
      <div
        className={`attachment-dropzone ${uploading ? 'attachment-dropzone--uploading' : ''}`}
        onDragOver={e => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        {uploading ? <span className="spinner" /> : <span>↑ Drop files here or click to upload</span>}
        <input
          ref={fileInputRef} type="file" multiple style={{ display: 'none' }}
          onChange={e => handleFiles([...e.target.files])}
        />
      </div>
    </div>
  );
}

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const icons = { pdf: '📄', png: '🖼', jpg: '🖼', jpeg: '🖼', gif: '🖼', svg: '🖼',
                  docx: '📝', doc: '📝', xlsx: '📊', xls: '📊', csv: '📊',
                  md: '📋', txt: '📋', yaml: '⚙', json: '⚙', zip: '📦', tar: '📦' };
  return icons[ext] || '📎';
}

// ---------------------------------------------------------------------------
// Discussion / Comments thread
// ---------------------------------------------------------------------------
export function DiscussionSection({ uid, currentUser = 'user' }) {
  const { toast } = useApp();
  const [comments, setComments] = useState([]);
  const [newText, setNewText] = useState('');
  const [replyTo, setReplyTo] = useState(null);
  const [editingUid, setEditingUid] = useState(null);
  const [editText, setEditText] = useState('');
  const [showResolved, setShowResolved] = useState(false);
  const textareaRef = useRef(null);

  const load = () => api.comments.list(uid).then(setComments).catch(() => {});
  useEffect(() => { load(); }, [uid]);

  const handlePost = async () => {
    const text = newText.trim();
    if (!text) return;
    try {
      await api.comments.add(uid, { text, author: currentUser, reply_to: replyTo });
      setNewText(''); setReplyTo(null);
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleEdit = async (commentUid) => {
    try {
      await api.comments.update(uid, commentUid, { text: editText });
      setEditingUid(null); setEditText('');
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleResolve = async (commentUid, resolved) => {
    try {
      await api.comments.resolve(uid, commentUid, resolved);
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleDelete = async (commentUid) => {
    try {
      await api.comments.delete(uid, commentUid);
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  // Build thread structure: top-level + replies
  const topLevel = comments.filter(c => !c.reply_to);
  const repliesTo = (parentUid) => comments.filter(c => c.reply_to === parentUid);
  const visible = showResolved ? topLevel : topLevel.filter(c => !c.resolved);
  const resolvedCount = topLevel.filter(c => c.resolved).length;

  const CommentNode = ({ comment, depth = 0 }) => (
    <div className={`comment-node ${comment.resolved ? 'comment-node--resolved' : ''}`}
         style={{ marginLeft: depth * 20 }}>
      <div className="comment-header">
        <span className="comment-author">{comment.author}</span>
        <span className="comment-date">{comment.created_at?.slice(0,10)}</span>
        {comment.updated_at && <span className="comment-edited text-muted">(edited)</span>}
        {comment.resolved && <span className="comment-resolved-badge">resolved</span>}
      </div>
      {editingUid === comment.uid ? (
        <div className="comment-edit-form">
          <textarea value={editText} onChange={e => setEditText(e.target.value)} rows={3} />
          <div className="comment-edit-actions">
            <button className="btn btn-primary" style={{ fontSize: 11 }} onClick={() => handleEdit(comment.uid)}>Save</button>
            <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setEditingUid(null)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="comment-body">{comment.text}</div>
      )}
      <div className="comment-actions">
        <button className="comment-action-btn" onClick={() => { setReplyTo(comment.uid); textareaRef.current?.focus(); }}>↩ Reply</button>
        {comment.author === currentUser && (
          <button className="comment-action-btn" onClick={() => { setEditingUid(comment.uid); setEditText(comment.text); }}>Edit</button>
        )}
        <button className="comment-action-btn" onClick={() => handleResolve(comment.uid, !comment.resolved)}>
          {comment.resolved ? 'Reopen' : '✓ Resolve'}
        </button>
        {comment.author === currentUser && (
          <button className="comment-action-btn comment-action-btn--danger" onClick={() => handleDelete(comment.uid)}>Delete</button>
        )}
      </div>
      {repliesTo(comment.uid).map(r => <CommentNode key={r.uid} comment={r} depth={depth + 1} />)}
    </div>
  );

  return (
    <div className="discussion-section">
      {resolvedCount > 0 && (
        <button className="btn btn-ghost" style={{ fontSize: 11, marginBottom: 8 }}
          onClick={() => setShowResolved(v => !v)}>
          {showResolved ? 'Hide' : 'Show'} {resolvedCount} resolved
        </button>
      )}

      {visible.length === 0 && !replyTo && (
        <div className="discussion-empty">No comments yet. Add the first one below.</div>
      )}

      {visible.map(c => <CommentNode key={c.uid} comment={c} />)}

      <div className="discussion-compose">
        {replyTo && (
          <div className="reply-indicator">
            Replying to thread
            <button className="btn btn-ghost" style={{ fontSize: 10 }} onClick={() => setReplyTo(null)}>✕</button>
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={newText}
          onChange={e => setNewText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handlePost(); }}
          placeholder={replyTo ? "Write a reply... (Ctrl+Enter to post)" : "Add a comment... (Ctrl+Enter to post)"}
          rows={3}
        />
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
          <button className="btn btn-primary" style={{ fontSize: 12 }} onClick={handlePost} disabled={!newText.trim()}>
            {replyTo ? 'Reply' : 'Comment'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom fields editor (schema management + value editing)
// ---------------------------------------------------------------------------
export function CustomFieldsPanel({ onClose }) {
  const { toast } = useApp();
  const [schema, setSchema] = useState([]);
  const [saving, setSaving] = useState(false);
  const TYPES = ['string','number','boolean','select','multiselect','date'];

  useEffect(() => {
    api.customFields.schema().then(setSchema).catch(() => {});
  }, []);

  const addField = () => setSchema(s => [...s, {
    key: '', label: '', type: 'string', options: [], required: false, description: '', default: null,
    applies_to: ['requirement'],
  }]);

  const updateField = (i, patch) => setSchema(s => s.map((f, j) => j === i ? { ...f, ...patch } : f));
  const removeField = (i) => setSchema(s => s.filter((_, j) => j !== i));

  const save = async () => {
    // Validate: all keys must be non-empty and unique
    const keys = schema.map(f => f.key.trim());
    if (keys.some(k => !k)) { toast('All fields must have a key', 'error'); return; }
    if (new Set(keys).size !== keys.length) { toast('Field keys must be unique', 'error'); return; }
    setSaving(true);
    try {
      await api.customFields.save(schema.map(f => ({ ...f, key: f.key.trim() })));
      toast('Custom field schema saved', 'success');
    } catch (err) { toast(err.message, 'error'); }
    finally { setSaving(false); }
  };

  return (
    <Panel title="Custom field schema" onClose={onClose} width={580}>
      <div className="import-hint">
        Define project-specific fields that appear on requirements. Values are stored in
        <code> custom_fields.key</code> in each YAML file. Schema lives in
        <code>.reqtool/custom_fields.yaml</code>.
      </div>

      {schema.map((field, i) => (
        <div key={i} className="custom-field-def">
          <div className="custom-field-def-row">
            <input value={field.key} onChange={e => updateField(i, { key: e.target.value })}
              placeholder="key (snake_case)" style={{ flex: 1 }} />
            <input value={field.label} onChange={e => updateField(i, { label: e.target.value })}
              placeholder="Display label" style={{ flex: 1 }} />
            <select value={field.type} onChange={e => updateField(i, { type: e.target.value })} style={{ flex: '0 0 100px' }}>
              {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, flexShrink: 0 }}>
              <input type="checkbox" checked={field.required} onChange={e => updateField(i, { required: e.target.checked })} style={{ width: 'auto' }} />
              Required
            </label>
            <button className="btn btn-ghost" style={{ color: 'var(--accent-red)', fontSize: 11 }} onClick={() => removeField(i)}>✕</button>
          </div>
          {(field.type === 'select' || field.type === 'multiselect') && (
            <input
              value={(field.options || []).join(', ')}
              onChange={e => updateField(i, { options: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
              placeholder="Options (comma-separated)"
              style={{ marginTop: 4, fontSize: 12 }}
            />
          )}
          <input value={field.description || ''} onChange={e => updateField(i, { description: e.target.value })}
            placeholder="Description (shown as hint)" style={{ marginTop: 4, fontSize: 12 }} />
        </div>
      ))}

      <button className="btn btn-secondary" onClick={addField}>+ Add field</button>

      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? <span className="spinner" /> : 'Save schema'}
        </button>
        <button className="btn btn-ghost" onClick={onClose}>Close</button>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Webhooks config panel
// ---------------------------------------------------------------------------
export function WebhooksPanel({ onClose }) {
  const { toast } = useApp();
  const [webhooks, setWebhooks] = useState([]);
  const [form, setForm] = useState({ url: '', events: ['status_changed','approved','comment_added'], secret: '', enabled: true });
  const [adding, setAdding] = useState(false);

  const load = () => api.webhooks.list().then(setWebhooks).catch(() => {});
  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!form.url.trim()) return;
    try {
      await api.webhooks.add({ ...form, url: form.url.trim(), secret: form.secret || null });
      setAdding(false); setForm({ url: '', events: ['status_changed','approved','comment_added'], secret: '', enabled: true });
      load(); toast('Webhook added', 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleDelete = async (idx) => {
    if (!confirm('Delete webhook?')) return;
    try { await api.webhooks.delete(idx); load(); toast('Deleted', 'info', 1500); }
    catch (err) { toast(err.message, 'error'); }
  };

  const ALL_EVENTS = ['status_changed','approved','comment_added','attachment_added'];

  return (
    <Panel title="Webhooks" onClose={onClose} width={520}>
      <div className="import-hint">
        Webhooks POST a JSON payload to your URL when events occur. Useful for Slack,
        Jira, ADO, or custom CI integrations. Set a secret to verify payloads with
        <code>X-Reqtool-Signature: sha256=...</code>.
      </div>

      {webhooks.map((wh, i) => (
        <div key={i} className="webhook-item">
          <div className="webhook-item-header">
            <span className="webhook-url mono">{wh.url}</span>
            <span className={`badge ${wh.enabled ? 'badge-approved' : 'badge-deprecated'}`}>
              {wh.enabled ? 'active' : 'disabled'}
            </span>
            <button className="btn btn-ghost" style={{ color: 'var(--accent-red)', fontSize: 11 }}
              onClick={() => handleDelete(i)}>✕</button>
          </div>
          <div className="webhook-events">
            {wh.events?.map(e => <span key={e} className="badge" style={{ fontSize: 9 }}>{e}</span>)}
          </div>
        </div>
      ))}

      {!adding && (
        <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }} onClick={() => setAdding(true)}>
          + Add webhook
        </button>
      )}
      {adding && (
        <div className="custom-field-def">
          <input value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
            placeholder="https://hooks.example.com/reqtool" />
          <input value={form.secret} onChange={e => setForm(f => ({ ...f, secret: e.target.value }))}
            placeholder="Signing secret (optional)" style={{ marginTop: 4 }} />
          <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {ALL_EVENTS.map(ev => (
              <label key={ev} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                <input type="checkbox"
                  checked={form.events.includes(ev)}
                  onChange={e => setForm(f => ({
                    ...f,
                    events: e.target.checked ? [...f.events, ev] : f.events.filter(x => x !== ev)
                  }))}
                  style={{ width: 'auto' }} />
                {ev}
              </label>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary" onClick={handleAdd} disabled={!form.url.trim()}>Add</button>
            <button className="btn btn-ghost" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}
    </Panel>
  );
}
