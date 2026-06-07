/**
 * Editor.jsx -- Main panel: requirement / principle / TBD editor.
 * All field sections from spec §10.4.
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';

// CodeMirror is loaded lazily so it never blocks initial render or tests.
// The plain textarea is always rendered first; CodeMirror replaces it once loaded.
// This also means the @uiw package is never part of the synchronous module graph,
// which prevents it from dragging in a second React copy at import time.
const CodeMirrorEditor = lazy(() =>
  import('@uiw/react-codemirror').then(mod => ({ default: mod.default }))
);
import { markdown } from '@codemirror/lang-markdown';
import { oneDark } from '@codemirror/theme-one-dark';
import { EditorView } from '@codemirror/view';

// Light theme for CodeMirror
const oneLight = EditorView.theme({
  '&': { background: '#ffffff', color: '#24292e' },
  '.cm-content': { caretColor: '#24292e' },
  '.cm-cursor': { borderLeftColor: '#24292e' },
  '.cm-selectionBackground, ::selection': { background: '#c8e1ff !important' },
  '.cm-gutters': { background: '#f6f8fa', borderRight: '1px solid #e1e4e8', color: '#6a737d' },
  '.cm-activeLineGutter': { background: '#fffbdd' },
  '.cm-activeLine': { background: '#fffbdd' },
  '.cm-line': { padding: '0 4px' },
}, { dark: false });
import { useApp } from '../AppContext';
import { api } from '../api';
import CommitModal from './CommitModal';
import { AttachmentsSection, DiscussionSection } from './Advanced';
import './Editor.css';

// Domain colours matching the JSX viewer
const DOMAIN_COLOURS = {
  need: '#64748b', sensing: '#0ea5e9', comms: '#a855f7', power: '#f59e0b',
  mechanical: '#f97316', thermal: '#fb7185', industrial: '#e879f9',
  security: '#e11d48', safety: '#fcd34d', compliance: '#64748b',
  ux: '#10b981', manufacture: '#84cc16', identity: '#06b6d4',
  firmware: '#8b5cf6', data: '#f472b6', cost: '#34d399', system: '#94a3b8',
};

function DomainBadge({ domain, style = {} }) {
  if (!domain) return null;
  const colour = DOMAIN_COLOURS[domain] || '#94a3b8';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
      background: colour + '22', color: colour,
      border: `1px solid ${colour}55`,
      ...style,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: colour, flexShrink: 0 }} />
      {domain}
    </span>
  );
}

function TypeBadge({ reqType, style = {} }) {
  if (!reqType) return null;
  const colours = {
    functional: '#1f6feb', performance: '#8957e5', safety: '#f85149',
    security: '#d29922', interface: '#39d353', stakeholder_need: '#64748b',
  };
  const colour = colours[reqType] || '#8b949e';
  return (
    <span style={{
      padding: '2px 7px', borderRadius: 4, fontSize: 11,
      background: colour + '22', color: colour,
      border: `1px solid ${colour}44`,
      ...style,
    }}>{reqType?.replace('_', ' ')}</span>
  );
}

// ---------------------------------------------------------------------------
function MarkdownEditor({ value, onChange, rows = 5 }) {
  const { state } = useApp();
  const isDark = state.theme !== 'light';
  const [preview, setPreview] = useState(false);
  const [renderedHtml, setRenderedHtml] = useState('');

  // Render via server when switching to preview
  useEffect(() => {
    if (!preview || !value) { setRenderedHtml(''); return; }
    api.render.markdown(value)
      .then(r => setRenderedHtml(r.html))
      .catch(() => setRenderedHtml(renderMarkdown(value))); // fallback
  }, [preview, value]);

  return (
    <div className="md-editor">
      <div className="md-editor-toolbar">
        <button className={`md-tab ${!preview ? 'active' : ''}`} onClick={() => setPreview(false)}>Edit</button>
        <button className={`md-tab ${preview ? 'active' : ''}`} onClick={() => setPreview(true)}>Preview</button>
      </div>
      {preview ? (
        <div className="md-preview" dangerouslySetInnerHTML={{ __html: renderedHtml || renderMarkdown(value || '') }} />
      ) : (
        <Suspense fallback={
          <textarea
            className="md-codemirror md-textarea-fallback"
            value={value || ''}
            rows={rows}
            onChange={e => onChange && onChange(e.target.value)}
            spellCheck={false}
          />
        }>
          <CodeMirrorEditor
            value={value || ''}
            height={`${rows * 22}px`}
            theme={isDark ? oneDark : oneLight}
            extensions={[markdown()]}
            onChange={onChange}
            basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: true }}
            className="md-codemirror"
          />
        </Suspense>
      )}
    </div>
  );
}

// Minimal Markdown renderer (no dep, handles basic inline + code blocks)
function renderMarkdown(text) {
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```[\s\S]*?```/g, m => `<pre><code>${m.slice(3, -3)}</code></pre>`)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^#{1,3} (.+)$/gm, (_, t) => `<strong>${t}</strong>`)
    .replace(/\n/g, '<br/>');
  return html;
}

// ---------------------------------------------------------------------------
// Controlled list editor -- picks from enum vocabulary, flags unknowns
// ---------------------------------------------------------------------------
function ControlledListEditor({ items = [], onChange, vocabulary = [], placeholder = 'Select or type...', allowFreeText = false }) {
  const [inputVal, setInputVal] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);

  const filtered = vocabulary.filter(v => 
    !items.includes(v) && v.toLowerCase().includes(inputVal.toLowerCase())
  );

  const add = (val) => {
    const v = val.trim();
    if (!v || items.includes(v)) return;
    onChange([...items, v]);
    setInputVal('');
    setShowDropdown(false);
  };

  const remove = (val) => onChange(items.filter(i => i !== val));

  return (
    <div className="controlled-list">
      <div className="controlled-list-chips">
        {items.map(item => {
          const known = vocabulary.length === 0 || vocabulary.includes(item);
          return (
            <span key={item} className={`chip ${known ? '' : 'chip--unknown'}`} title={known ? '' : 'Not in vocabulary -- add it in Vocabularies'}>
              {item}
              {!known && <span className="chip-warn">⚠</span>}
              <button className="chip-remove" onClick={() => remove(item)}>✕</button>
            </span>
          );
        })}
      </div>
      <div className="controlled-list-input" style={{ position: 'relative' }}>
        <input
          value={inputVal}
          onChange={e => { setInputVal(e.target.value); setShowDropdown(true); }}
          onFocus={() => setShowDropdown(true)}
          onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
          onKeyDown={e => {
            if (e.key === 'Enter') { e.preventDefault(); if (filtered[0]) add(filtered[0]); else if (allowFreeText) add(inputVal); }
            if (e.key === 'Escape') setShowDropdown(false);
          }}
          placeholder={placeholder}
        />
        {showDropdown && (filtered.length > 0 || (allowFreeText && inputVal.trim())) && (
          <div className="controlled-list-dropdown">
            {filtered.map(v => (
              <div key={v} className="controlled-list-option" onMouseDown={() => add(v)}>
                {v}
              </div>
            ))}
            {allowFreeText && inputVal.trim() && !vocabulary.includes(inputVal.trim()) && (
              <div className="controlled-list-option controlled-list-option--new" onMouseDown={() => add(inputVal.trim())}>
                <span style={{ color: 'var(--text-muted)', fontSize: 10, marginRight: 4 }}>NEW</span>
                {inputVal.trim()}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// String list editor (free-text -- for constraints, assumptions, reviewers)
// ---------------------------------------------------------------------------
function Field({ label, children, hint }) {
  return (
    <div className="field-group">
      <label className="field-label">{label}{hint && <span className="field-hint">{hint}</span>}</label>
      {children}
    </div>
  );
}

function EnumSelect({ value, options = [], onChange, nullable = true }) {
  return (
    <select value={value ?? ''} onChange={e => onChange(e.target.value || null)}>
      {nullable && <option value="">—</option>}
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

function StringListEditor({ items = [], onChange, placeholder = 'Add item...' }) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const t = draft.trim();
    if (t && !items.includes(t)) { onChange([...items, t]); setDraft(''); }
  };
  return (
    <div className="string-list">
      <div className="string-list-items">
        {items.map((item, i) => (
          <div key={i} className="string-list-item">
            <span>{item}</span>
            <button className="string-list-remove" onClick={() => onChange(items.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
      </div>
      <div className="string-list-add">
        <input value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()} placeholder={placeholder} />
        <button className="btn btn-secondary" onClick={add}>Add</button>
      </div>
    </div>
  );
}

function Section({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="editor-section">
      <div className="editor-section-header" onClick={() => setOpen(o => !o)}>
        <span className="editor-section-toggle">{open ? '▾' : '▸'}</span>
        <span className="editor-section-title">{title}</span>
      </div>
      {open && <div className="editor-section-body">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AC links sub-editor
// ---------------------------------------------------------------------------
function ACLinksEditor({ links = [], onChange, enums }) {
  const [form, setForm] = useState({ system: 'test_management', type: 'test_case', ref: '', title: '' });
  const add = () => {
    if (!form.ref.trim()) return;
    onChange([...links, { ...form }]);
    setForm({ system: 'test_management', type: 'test_case', ref: '', title: '' });
  };
  const remove = (i) => onChange(links.filter((_, j) => j !== i));
  const linkSystems = enums?.link_system || ['test_management', 'jira', 'github', 'gitlab', 'sharepoint', 'other'];
  const linkTypes = enums?.link_type || ['test_case', 'test_suite', 'defect', 'backlog_item', 'review', 'other'];
  return (
    <div className="ac-links-editor">
      {links.map((link, i) => (
        <div key={i} className="ac-link-row">
          <span className="badge" style={{ fontSize: 9 }}>{link.system}</span>
          <span className="badge" style={{ background: 'rgba(88,166,255,.15)', color: 'var(--text-link)', fontSize: 9 }}>{link.type}</span>
          <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{link.ref}</span>
          {link.title && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{link.title}</span>}
          <button className="string-list-remove" onClick={() => remove(i)}>✕</button>
        </div>
      ))}
      <div className="ac-links-add">
        <select value={form.system} onChange={e => setForm(f => ({ ...f, system: e.target.value }))} style={{ flex: '0 0 130px' }}>
          {linkSystems.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))} style={{ flex: '0 0 110px' }}>
          {linkTypes.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <input value={form.ref} onChange={e => setForm(f => ({ ...f, ref: e.target.value }))} placeholder="ref" style={{ flex: 1 }} />
        <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="title (opt)" style={{ flex: 1 }} />
        <button className="btn btn-secondary" onClick={add} style={{ height: 28, whiteSpace: 'nowrap', flexShrink: 0 }}>Add</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Acceptance Criteria editor
// ---------------------------------------------------------------------------
function ACEditor({ acs = [], onChange, enums }) {
  const [draftText, setDraftText] = useState('');
  const addAc = () => {
    const text = draftText.trim();
    if (!text) return;
    onChange([...acs, { uid: `new-${Date.now()}`, id: `AC-${Date.now()}`, text, links: [] }]);
    setDraftText('');
  };
  const updateText = (idx, text) => onChange(acs.map((ac, i) => i === idx ? { ...ac, text } : ac));
  const updateLinks = (idx, links) => onChange(acs.map((ac, i) => i === idx ? { ...ac, links } : ac));
  const [expandedAc, setExpandedAc] = useState(null);
  const remove = (idx) => onChange(acs.filter((_, i) => i !== idx));
  return (
    <div className="ac-editor">
      {acs.map((ac, idx) => (
        <div key={ac.uid} className="ac-item">
          <div className="ac-item-header">
            <span className="ac-id mono">{ac.id}</span>
            <button
              className="btn btn-ghost"
              style={{ fontSize: 10, padding: '2px 6px' }}
              onClick={() => setExpandedAc(expandedAc === idx ? null : idx)}
              title="Edit links for this criterion"
            >
              {(ac.links?.length || 0) > 0 ? `${ac.links.length} link(s)` : '+ links'}
            </button>
            <button className="ac-remove" onClick={() => remove(idx)}>✕</button>
          </div>
          <textarea value={ac.text || ''} rows={3} onChange={e => updateText(idx, e.target.value)} />
          {expandedAc === idx && (
            <div className="ac-links-wrap">
              <ACLinksEditor links={ac.links || []} onChange={links => updateLinks(idx, links)} enums={enums} />
            </div>
          )}
        </div>
      ))}
      <div className="ac-add">
        <textarea value={draftText} onChange={e => setDraftText(e.target.value)} rows={2} placeholder="Given... When... Then..." />
        <button className="btn btn-secondary" style={{ marginTop: 4 }} onClick={addAc}>+ Add criterion</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Attributes editor (key/value with reserved key autocomplete)
// ---------------------------------------------------------------------------
const RESERVED_ATTRS = [
  'variant_', 'reusable', 'nfr', 'negative', 'status_condition',
  'source', 'source_ref', 'source_document', 'baseline', 'maturity',
];

function AttributesEditor({ attrs = {}, onChange }) {
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');

  const set = (key, val) => onChange({ ...attrs, [key]: val });
  const del = (key) => { const n = { ...attrs }; delete n[key]; onChange(n); };
  const add = () => {
    const k = newKey.trim();
    if (!k) return;
    onChange({ ...attrs, [k]: newVal });
    setNewKey(''); setNewVal('');
  };

  return (
    <div className="attrs-editor">
      {Object.entries(attrs).map(([key, val]) => (
        <div key={key} className="attr-row">
          <span className="attr-key mono">{key}</span>
          {typeof val === 'boolean' ? (
            <input type="checkbox" checked={val} onChange={e => set(key, e.target.checked)} style={{ width: 'auto' }} />
          ) : (
            <input value={String(val)} onChange={e => set(key, e.target.value)} style={{ flex: 1 }} />
          )}
          <button className="string-list-remove" onClick={() => del(key)}>✕</button>
        </div>
      ))}
      <div className="attr-add">
        <input
          value={newKey}
          onChange={e => setNewKey(e.target.value)}
          placeholder="key"
          list="attr-suggestions"
          style={{ flex: 1 }}
        />
        <datalist id="attr-suggestions">
          {RESERVED_ATTRS.map(k => <option key={k} value={k} />)}
        </datalist>
        <input value={newVal} onChange={e => setNewVal(e.target.value)} placeholder="value" style={{ flex: 1 }} />
        <button className="btn btn-secondary" onClick={add}>Add</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NFR editor (numeric key/value)
// ---------------------------------------------------------------------------
function NfrEditor({ nfr = {}, nfrKeys = [], onChange }) {
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');

  const set = (key, val) => {
    const n = parseFloat(val);
    onChange({ ...nfr, [key]: isNaN(n) ? val : n });
  };
  const del = (key) => { const n = { ...nfr }; delete n[key]; onChange(n); };
  const add = () => {
    const k = newKey.trim();
    if (!k) return;
    const n = parseFloat(newVal);
    onChange({ ...nfr, [k]: isNaN(n) ? newVal : n });
    setNewKey(''); setNewVal('');
  };

  return (
    <div className="attrs-editor">
      {Object.entries(nfr).map(([key, val]) => (
        <div key={key} className="attr-row">
          <span className={`attr-key mono ${nfrKeys.length && !nfrKeys.includes(key) ? 'attr-key-warn' : ''}`} title={nfrKeys.length && !nfrKeys.includes(key) ? 'Key not in enums.yaml nfr_keys' : ''}>
            {key}{nfrKeys.length && !nfrKeys.includes(key) ? ' ⚠' : ''}
          </span>
          <input type="number" value={val} onChange={e => set(key, e.target.value)} style={{ flex: 1 }} />
          <button className="string-list-remove" onClick={() => del(key)}>✕</button>
        </div>
      ))}
      <div className="attr-add">
        <input value={newKey} onChange={e => setNewKey(e.target.value)} placeholder="key (e.g. latency_ms)" list="nfr-keys-list" style={{ flex: 1 }} />
        <datalist id="nfr-keys-list">{nfrKeys.map(k => <option key={k} value={k} />)}</datalist>
        <input type="number" value={newVal} onChange={e => setNewVal(e.target.value)} placeholder="value" style={{ flex: 1 }} />
        <button className="btn btn-secondary" onClick={add}>Add</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Relationships editor
// ---------------------------------------------------------------------------
function RelationshipsEditor({ rels = [], onChange, enums, excludeUid }) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [newType, setNewType] = useState('derived_from');
  const searchRef = useRef(null);

  const doSearch = useCallback(async (q) => {
    if (!q.trim()) { setResults([]); return; }
    try {
      const r = await api.search(q);
      setResults(r.filter(x => x.uid !== excludeUid));
    } catch { setResults([]); }
  }, [excludeUid]);

  useEffect(() => {
    const t = setTimeout(() => doSearch(search), 250);
    return () => clearTimeout(t);
  }, [search, doSearch]);

  const addRel = (targetUid, targetId, targetTitle) => {
    if (rels.some(r => r.target?.uid === targetUid && r.type === newType)) return;
    onChange([...rels, { type: newType, target: { uid: targetUid }, _display: `${targetId} — ${targetTitle}` }]);
    setSearch(''); setResults([]);
  };

  const remove = (idx) => onChange(rels.filter((_, i) => i !== idx));

  return (
    <div className="rels-editor">
      {rels.map((rel, idx) => (
        <div key={idx} className="rel-row">
          <span className="rel-type badge">{rel.type}</span>
          <span className="rel-target mono">{rel._display || rel.target?.uid?.slice(0, 12) + '...'}</span>
          <button className="string-list-remove" onClick={() => remove(idx)}>✕</button>
        </div>
      ))}
      <div className="rel-add">
        <select value={newType} onChange={e => setNewType(e.target.value)} style={{ flex: '0 0 160px' }}>
          {(enums?.relationship_type || []).map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="rel-search-wrap">
          <input
            ref={searchRef}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by ID or title..."
          />
          {results.length > 0 && (
            <div className="rel-dropdown">
              {results.map(r => (
                <div key={r.uid} className="rel-option" onClick={() => addRel(r.uid, r.id, r.title)}>
                  <span className="mono" style={{ fontSize: 11 }}>{r.id}</span>
                  <span style={{ color: 'var(--text-secondary)', marginLeft: 6 }}>{r.title}</span>
                  <span className="badge" style={{ marginLeft: 6, fontSize: 9 }}>{r.type}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Links editor (external references) with tool presets
// ---------------------------------------------------------------------------
const LINK_PRESETS = [
  { system: 'jira',   type: 'backlog_item', label: 'Jira',    placeholder: 'PROJECT-123' },
  { system: 'ado',    type: 'work_item',    label: 'ADO',     placeholder: 'AB#12345' },
  { system: 'github', type: 'issue',        label: 'GitHub',  placeholder: 'owner/repo#123' },
  { system: 'github', type: 'pull_request', label: 'PR',      placeholder: 'owner/repo#456' },
  { system: 'gitlab', type: 'issue',        label: 'GitLab',  placeholder: 'group/repo#78' },
  { system: 'git',    type: 'commit',       label: 'Commit',  placeholder: 'abc1234' },
  { system: 'git',    type: 'tag',          label: 'Git tag', placeholder: 'v1.2.3' },
];

function LinksEditor({ links = [], onChange, enums }) {
  const [form, setForm] = useState({ system: 'jira', type: 'backlog_item', ref: '', title: '', system_name: '' });
  const [showFull, setShowFull] = useState(false);

  const addLink = (system, type, ref, title = '') => {
    if (!ref.trim()) return;
    onChange([...links, { system, type, ref, title, ref_type: 'id', system_name: '' }]);
  };

  const addFromForm = () => {
    if (!form.ref.trim()) return;
    onChange([...links, { ...form }]);
    setForm({ system: 'jira', type: 'backlog_item', ref: '', title: '', system_name: '' });
    setShowFull(false);
  };

  const remove = (idx) => onChange(links.filter((_, i) => i !== idx));

  const SYSTEM_ICONS = { jira: '◉', ado: '◈', github: '◎', gitlab: '◉', git: '⑂', other: '⊞' };

  return (
    <div className="links-editor">
      {links.map((link, idx) => (
        <div key={idx} className="link-row">
          <span className="link-system-icon">{SYSTEM_ICONS[link.system] || '⊞'}</span>
          <span className="badge" style={{ fontSize: 10 }}>{link.system}</span>
          <span className="badge" style={{ background: 'rgba(88,166,255,.15)', color: 'var(--text-link)', fontSize: 10 }}>{link.type}</span>
          {link.ref.startsWith('http') ? (
            <a href={link.ref} target="_blank" rel="noopener noreferrer" className="link-ref mono">{link.title || link.ref}</a>
          ) : (
            <span className="link-ref mono">{link.ref}</span>
          )}
          {link.title && !link.ref.startsWith('http') && <span className="link-title">{link.title}</span>}
          <button className="string-list-remove" onClick={() => remove(idx)}>✕</button>
        </div>
      ))}

      {/* Quick-add preset buttons */}
      <div className="link-presets">
        {LINK_PRESETS.map((p, i) => (
          <QuickLinkButton key={i} preset={p} onAdd={addLink} />
        ))}
        <button
          className={`link-preset-btn ${showFull ? 'active' : ''}`}
          onClick={() => setShowFull(v => !v)}
          title="Custom link"
        >+ Custom</button>
      </div>

      {showFull && (
        <div className="link-form">
          <select value={form.system} onChange={e => setForm(f => ({ ...f, system: e.target.value }))} style={{ flex: '0 0 110px' }}>
            {(enums?.link_system || ['jira','ado','github','gitlab','git','sharepoint','confluence','other']).map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))} style={{ flex: '0 0 120px' }}>
            {(enums?.link_type || ['backlog_item','work_item','issue','pull_request','commit','tag','defect','test_case','review','document','other']).map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input value={form.ref} onChange={e => setForm(f => ({ ...f, ref: e.target.value }))} placeholder="ref, ID, or URL" style={{ flex: 1 }} />
          <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="title (optional)" style={{ flex: 1 }} />
          <button className="btn btn-primary" style={{ height: 28, whiteSpace: 'nowrap', flexShrink: 0 }} onClick={addFromForm}>Add</button>
        </div>
      )}
    </div>
  );
}

function QuickLinkButton({ preset, onAdd }) {
  const [ref, setRef] = useState('');
  const [active, setActive] = useState(false);
  if (!active) {
    return (
      <button className="link-preset-btn" onClick={() => setActive(true)} title={`Add ${preset.label} link`}>
        + {preset.label}
      </button>
    );
  }
  return (
    <div className="link-quick-input">
      <span className="link-preset-label">{preset.label}</span>
      <input
        autoFocus
        value={ref}
        onChange={e => setRef(e.target.value)}
        placeholder={preset.placeholder}
        onKeyDown={e => {
          if (e.key === 'Enter') { onAdd(preset.system, preset.type, ref); setRef(''); setActive(false); }
          if (e.key === 'Escape') { setActive(false); setRef(''); }
        }}
        style={{ width: 130, height: 26, fontSize: 11 }}
      />
      <button className="btn btn-primary" style={{ height: 26, fontSize: 11, padding: '0 8px' }}
        onClick={() => { onAdd(preset.system, preset.type, ref); setRef(''); setActive(false); }}>
        Add
      </button>
      <button className="btn btn-ghost" style={{ height: 26, fontSize: 11 }} onClick={() => { setActive(false); setRef(''); }}>✕</button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Parent picker (search-based replacement for parentId text input)
// ---------------------------------------------------------------------------
function ParentPicker({ value, onChange, excludeUid }) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [label, setLabel] = useState('');

  // Resolve existing parentId to a label
  useEffect(() => {
    if (!value) { setLabel(''); return; }
    api.requirements.get(value)
      .then(r => setLabel(`${r.id} — ${r.title}`))
      .catch(() => setLabel(value.slice(0, 12) + '...'));
  }, [value]);

  useEffect(() => {
    if (!search.trim()) { setResults([]); return; }
    const t = setTimeout(() => {
      api.search(search).then(r => setResults(r.filter(x => x.uid !== excludeUid && x.type === 'requirement')));
    }, 250);
    return () => clearTimeout(t);
  }, [search, excludeUid]);

  const select = (uid, id, title) => {
    onChange(uid);
    setLabel(`${id} — ${title}`);
    setSearch(''); setResults([]);
  };

  const clear = () => { onChange(null); setLabel(''); setSearch(''); };

  return (
    <div className="parent-picker">
      {value ? (
        <div className="parent-picker-value">
          <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', flex: 1 }}>{label || value}</span>
          <button className="string-list-remove" onClick={clear} title="Remove parent">✕</button>
        </div>
      ) : (
        <div className="rel-search-wrap">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by ID or title..."
          />
          {results.length > 0 && (
            <div className="rel-dropdown">
              {results.map(r => (
                <div key={r.uid} className="rel-option" onClick={() => select(r.uid, r.id, r.title)}>
                  <span className="mono" style={{ fontSize: 11 }}>{r.id}</span>
                  <span style={{ color: 'var(--text-secondary)', marginLeft: 6, fontSize: 12 }}>{r.title}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline validation summary
// ---------------------------------------------------------------------------
function ValidationSummary({ issues }) {
  if (!issues) return null;
  const errors = issues.errors || [];
  const warnings = issues.warnings || [];
  if (!errors.length && !warnings.length) return (
    <div className="inline-val inline-val--pass">✓ No issues</div>
  );
  return (
    <div className="inline-val">
      {errors.map((e, i) => (
        <div key={i} className="inline-val-item inline-val-item--error">
          <span className="inline-val-code">{e.code}</span>
          <span>{e.message}</span>
        </div>
      ))}
      {warnings.map((w, i) => (
        <div key={i} className="inline-val-item inline-val-item--warn">
          <span className="inline-val-code">{w.code}</span>
          <span>{w.message}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom fields value editor (reads schema, renders appropriate inputs)
// ---------------------------------------------------------------------------
function CustomFieldsValueEditor({ schema, values, onChange }) {
  const set = (key, val) => onChange({ ...values, [key]: val });

  return (
    <div className="attrs-editor">
      {schema.filter(f => f.applies_to?.includes('requirement') !== false).map(field => (
        <div key={field.key} className="attr-row">
          <span className="attr-key mono" title={field.description}>
            {field.label || field.key}
            {field.required && <span style={{ color: 'var(--accent-red)', marginLeft: 2 }}>*</span>}
          </span>
          {field.type === 'boolean' ? (
            <input type="checkbox" checked={!!values[field.key]}
              onChange={e => set(field.key, e.target.checked)} style={{ width: 'auto' }} />
          ) : field.type === 'number' ? (
            <input type="number" value={values[field.key] ?? ''}
              onChange={e => set(field.key, e.target.value === '' ? null : Number(e.target.value))}
              style={{ flex: 1 }} />
          ) : field.type === 'date' ? (
            <input type="date" value={values[field.key]?.slice(0, 10) ?? ''}
              onChange={e => set(field.key, e.target.value || null)} style={{ flex: 1 }} />
          ) : field.type === 'select' ? (
            <select value={values[field.key] ?? ''} onChange={e => set(field.key, e.target.value || null)} style={{ flex: 1 }}>
              <option value="">—</option>
              {field.options?.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : field.type === 'multiselect' ? (
            <ControlledListEditor
              items={Array.isArray(values[field.key]) ? values[field.key] : []}
              onChange={v => set(field.key, v)}
              vocabulary={field.options || []}
              placeholder={`Select ${field.label || field.key}...`}
            />
          ) : (
            <input value={values[field.key] ?? ''} onChange={e => set(field.key, e.target.value || null)}
              style={{ flex: 1 }} placeholder={field.description} />
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
function WorkflowStateWidget({ uid, status, onTransition }) {
  const { state } = useApp();
  const wf = state.workflow;
  if (!wf?.states?.length) return null;

  const currentState = wf.states.find(s => s.id === status);
  const transitions = (wf.transitions?.[status] || [])
    .map(id => wf.states.find(s => s.id === id))
    .filter(Boolean);

  if (!currentState) return null;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span
        className="wf-current-state"
        style={{ color: currentState.colour, borderColor: currentState.colour + '44', background: currentState.colour + '15' }}
      >
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: currentState.colour, flexShrink: 0 }} />
        {currentState.label}
      </span>
      {transitions.map(t => (
        <button
          key={t.id}
          className="wf-transition-btn"
          style={{ color: t.colour, borderColor: t.colour + '55', background: t.colour + '12' }}
          onClick={() => onTransition(t.id)}
          title={`Move to ${t.label}`}
        >→ {t.label}</button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Requirement editor
// ---------------------------------------------------------------------------
function RequirementEditor({ uid }) {
  const { state, dispatch, toast } = useApp();
  const { enums } = state;
  const [req, setReq] = useState(null);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showCommit, setShowCommit] = useState(false);
  const [history, setHistory] = useState(null);
  const [breadcrumb, setBreadcrumb] = useState([]);
  const [validationIssues, setValidationIssues] = useState(null); // {errors, warnings} | null

  useEffect(() => {
    setLoading(true);
    api.requirements.get(uid)
      .then(data => {
        setReq(data); setDraft(data);
        // Build breadcrumb by walking parentId chain
        const crumbs = [];
        const buildCrumbs = async (parentId) => {
          if (!parentId) return;
          try {
            const parent = await api.requirements.get(parentId);
            crumbs.unshift({ uid: parent.uid, id: parent.id, title: parent.title });
            if (parent.parentId) await buildCrumbs(parent.parentId);
          } catch { /* parent may not exist */ }
        };
        buildCrumbs(data.parentId).then(() => setBreadcrumb(crumbs));
      })
      .catch(err => toast(err.message, 'error'))
      .finally(() => setLoading(false));
  }, [uid]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(req);

  useEffect(() => {
    if (isDirty) dispatch({ type: 'MARK_DIRTY', uid });
    else dispatch({ type: 'MARK_CLEAN', uid });
  }, [isDirty, uid]);

  // Ctrl+S save shortcut
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (isDirty && !saving) handleSave();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isDirty, saving, draft]);

  const patch = useCallback((field, value) => setDraft(d => ({ ...d, [field]: value })), []);
  const patchContent = useCallback((field, value) => setDraft(d => ({ ...d, content: { ...d.content, [field]: value } })), []);
  const patchBlock = useCallback((block, field, value) => setDraft(d => ({ ...d, [block]: { ...d[block], [field]: value } })), []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await api.requirements.update(uid, draft);
      setReq(updated); setDraft(updated);
      dispatch({ type: 'MARK_CLEAN', uid });
      // Inline validation after save
      const issues = await api.validate.single(uid).catch(() => null);
      setValidationIssues(issues);
      const errCount = issues?.errors?.length || 0;
      const warnCount = issues?.warnings?.length || 0;
      if (errCount) toast(`Saved with ${errCount} error(s)`, 'error', 4000);
      else if (warnCount) toast(`Saved (${warnCount} warning(s))`, 'info', 3000);
      else toast('Saved', 'success');
    } catch (err) { toast(err.message, 'error'); }
    finally { setSaving(false); }
  };

  const handleCommit = async (message, increment, changeRef) => {
    setSaving(true);
    try {
      if (isDirty) {
        const updated = await api.requirements.update(uid, draft);
        setReq(updated); setDraft(updated);
      }
      const result = await api.requirements.commit(uid, { message, increment, change_ref: changeRef });
      toast(`Committed: ${result.commit_sha?.slice(0, 7)}`, 'success');
      setShowCommit(false);
      dispatch({ type: 'COMMITTED' });
      const updated = await api.requirements.get(uid);
      setReq(updated); setDraft(updated);
    } catch (err) { toast(err.message, 'error'); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="editor-loading"><div className="spinner" /></div>;
  if (!draft) return <div className="editor-empty">Could not load requirement.</div>;

  const nfrKeys = enums?.nfr_keys || [];

  return (
    <div className="editor">
      {breadcrumb.length > 0 && (
        <div className="editor-breadcrumb">
          {breadcrumb.map((crumb, i) => (
            <span key={crumb.uid}>
              {i > 0 && <span className="breadcrumb-sep"> › </span>}
              <button
                className="breadcrumb-item"
                onClick={() => dispatch({ type: 'SELECT', uid: crumb.uid, artefactType: 'requirement' })}
              >
                {crumb.id}
              </button>
            </span>
          ))}
          <span className="breadcrumb-sep"> › </span>
          <span className="breadcrumb-current">{draft.id}</span>
        </div>
      )}
      <div className="editor-header">
        <div className="editor-header-left">
          <div className="copy-uid-wrap">
            <span className="editor-id mono">{draft.id}</span>
            <button
              className="copy-uid-btn"
              title="Copy UID to clipboard"
              onClick={() => {
                navigator.clipboard.writeText(uid).then(() => toast('UID copied', 'success', 1500));
              }}
            >⎘</button>
          </div>
          <span className="editor-version mono text-muted">v{draft.version}</span>
          <DomainBadge domain={draft.domain} />
          <TypeBadge reqType={draft.req_type} />
          <WorkflowStateWidget uid={uid} status={draft.status} onTransition={v => patch('status', v)} />
          {isDirty && <span className="editor-dirty-badge">unsaved</span>}
        </div>
        <div className="editor-header-right">
          <button
            className="btn btn-ghost"
            title="Open in new tab"
            onClick={() => window.open(`${window.location.pathname}?uid=${uid}&type=requirement`, '_blank')}
            style={{ fontSize: 13, padding: '4px 8px' }}
          >⧉</button>
          <button className="btn btn-secondary" onClick={handleSave} disabled={!isDirty || saving}>
            {saving ? <span className="spinner" /> : 'Save'}
          </button>
          <button className="btn btn-primary" onClick={() => setShowCommit(true)} disabled={saving}>
            Save &amp; Commit
          </button>
        </div>
      </div>

      <div className="editor-body">
        {validationIssues && <ValidationSummary issues={validationIssues} />}
        {/* Identity */}
        <Section title="Identity">
          <div className="field-row">
            <Field label="ID"><input value={draft.id ?? ''} onChange={e => patch('id', e.target.value)} /></Field>
            <Field label="Parent requirement">
              <ParentPicker value={draft.parentId} onChange={v => patch('parentId', v)} excludeUid={uid} />
            </Field>
          </div>
          <Field label="Title"><input value={draft.title ?? ''} onChange={e => patch('title', e.target.value)} /></Field>
        </Section>

        {/* Content */}
        <Section title="Content">
          <Field label="Description (shall statement)">
            <MarkdownEditor value={draft.content?.description} onChange={v => patchContent('description', v)} rows={6} />
          </Field>
          <Field label="Rationale">
            <MarkdownEditor value={draft.content?.rationale} onChange={v => patchContent('rationale', v)} rows={4} />
          </Field>
          <Field label="Extended Description">
            <MarkdownEditor value={draft.content?.extended_description} onChange={v => patchContent('extended_description', v)} rows={4} />
          </Field>
        </Section>

        {/* Acceptance Criteria */}
        <Section title="Acceptance Criteria">
          <ACEditor acs={draft.acceptance_criteria ?? []} onChange={v => patch('acceptance_criteria', v)} enums={enums} />
        </Section>

        {/* Classification */}
        <Section title="Classification">
          <div className="field-row">
            <Field label="Status"><EnumSelect value={draft.status} options={enums?.status || []} onChange={v => patch('status', v)} nullable={false} /></Field>
            <Field label="Priority"><EnumSelect value={draft.priority} options={enums?.priority || []} onChange={v => patch('priority', v)} nullable={false} /></Field>
          </div>
          <div className="field-row">
            <Field label="Type"><EnumSelect value={draft.req_type} options={enums?.req_type || []} onChange={v => patch('req_type', v)} nullable={false} /></Field>
            <Field label="Domain">
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <EnumSelect value={draft.domain} options={enums?.domain || []} onChange={v => patch('domain', v)} />
                <DomainBadge domain={draft.domain} />
              </div>
            </Field>
          </div>
          <div className="field-row">
            <Field label="Feature"><EnumSelect value={draft.feature} options={enums?.feature || []} onChange={v => patch('feature', v)} /></Field>
            <Field label="Discipline"><EnumSelect value={draft.discipline} options={enums?.discipline || []} onChange={v => patch('discipline', v)} /></Field>
          </div>
          <div className="field-row">
            <Field label="Risk"><EnumSelect value={draft.risk} options={enums?.risk_level || []} onChange={v => patch('risk', v)} /></Field>
            <Field label="Component"><EnumSelect value={draft.component} options={enums?.component || []} onChange={v => patch('component', v)} /></Field>
          </div>
        </Section>

        {/* Relationships -- open by default */}
        <Section title="Relationships" defaultOpen={true}>
          <RelationshipsEditor
            rels={draft.relationships ?? []}
            onChange={v => patch('relationships', v)}
            enums={enums}
            excludeUid={uid}
          />
        </Section>

        {/* External Links -- open by default */}
        <Section title="External Links" defaultOpen={true}>
          <LinksEditor links={draft.links ?? []} onChange={v => patch('links', v)} enums={enums} />
        </Section>

        {/* Ownership */}
        <Section title="Ownership" defaultOpen={false}>
          <Field label="Owner" hint="from people list">
            <ControlledListEditor
              items={draft.owner ? [draft.owner] : []}
              onChange={v => patch('owner', v[v.length - 1] || null)}
              vocabulary={enums?.owner || []}
              placeholder="Select owner..."
              allowFreeText={true}
            />
          </Field>
          <Field label="Allocated To" hint="teams from vocabulary">
            <ControlledListEditor
              items={draft.allocated_to ?? []}
              onChange={v => patch('allocated_to', v)}
              vocabulary={enums?.team || []}
              placeholder="Select team..."
            />
          </Field>
          <Field label="Tags" hint="from vocabulary">
            <ControlledListEditor
              items={draft.tags ?? []}
              onChange={v => patch('tags', v)}
              vocabulary={enums?.tags || []}
              placeholder="Select tag..."
            />
          </Field>
        </Section>

        {/* Attributes */}
        <Section title="Attributes" defaultOpen={false}>
          <AttributesEditor attrs={draft.attributes ?? {}} onChange={v => patch('attributes', v)} />
        </Section>

        {/* Custom Fields -- schema-driven */}
        {enums?._customFieldSchema?.length > 0 && (
          <Section title="Custom Fields" defaultOpen={true}>
            <CustomFieldsValueEditor
              schema={enums._customFieldSchema}
              values={draft.custom_fields ?? {}}
              onChange={v => patch('custom_fields', v)}
            />
          </Section>
        )}

        {/* NFR */}
        <Section title="NFR Constraints" defaultOpen={false}>
          <NfrEditor nfr={draft.nfr ?? {}} nfrKeys={nfrKeys} onChange={v => patch('nfr', v)} />
        </Section>

        {/* Constraints & Assumptions */}
        <Section title="Constraints & Assumptions" defaultOpen={false}>
          <Field label="Constraints">
            <StringListEditor items={draft.constraints ?? []} onChange={v => patch('constraints', v)} placeholder="Add constraint..." />
          </Field>
          <Field label="Assumptions">
            <StringListEditor items={draft.assumptions ?? []} onChange={v => patch('assumptions', v)} placeholder="Add assumption..." />
          </Field>
        </Section>

        {/* Safety */}
        <Section title="Safety" defaultOpen={false}>
          <div className="field-row">
            <Field label="Safety Related">
              <label className="toggle-label">
                <input type="checkbox" checked={draft.safety_related ?? false} onChange={e => patch('safety_related', e.target.checked)} />
                <span style={{ marginLeft: 6 }}>Safety related</span>
              </label>
            </Field>
            <Field label="Safety Classification" hint="from vocabulary">
              <ControlledListEditor
                items={draft.safety_classification ? [draft.safety_classification] : []}
                onChange={v => patch('safety_classification', v[v.length - 1] || null)}
                vocabulary={enums?.safety_class || []}
                placeholder="e.g. SIL-2, ASIL-B..."
                allowFreeText={true}
              />
            </Field>
          </div>
        </Section>

        {/* Verification */}
        <Section title="Verification" defaultOpen={false}>
          <div className="field-row">
            <Field label="Method"><EnumSelect value={draft.verification_method} options={enums?.verification_method || []} onChange={v => patch('verification_method', v)} nullable={false} /></Field>
            <Field label="Status"><EnumSelect value={draft.verification?.status} options={enums?.verification_status || []} onChange={v => patchBlock('verification', 'status', v)} /></Field>
          </div>
          <div className="field-row">
            <Field label="Verified Date">
              <input type="date" value={draft.verification?.verified_date?.slice(0, 10) ?? ''}
                onChange={e => patchBlock('verification', 'verified_date', e.target.value || null)} />
            </Field>
          </div>
          <Field label="Note">
            <textarea value={draft.verification?.note ?? ''} rows={2}
              onChange={e => patchBlock('verification', 'note', e.target.value)} />
          </Field>
        </Section>

        {/* Approval */}
        <Section title="Approval" defaultOpen={false}>
          <div className="field-row">
            <Field label="Status"><EnumSelect value={draft.approval?.status} options={enums?.approval_status || []} onChange={v => patchBlock('approval', 'status', v)} /></Field>
            <Field label="Approved By" hint="from people list">
              <ControlledListEditor
                items={draft.approval?.approved_by ? [draft.approval.approved_by] : []}
                onChange={v => patchBlock('approval', 'approved_by', v[v.length - 1] || null)}
                vocabulary={enums?.owner || []}
                placeholder="Select person..."
                allowFreeText={true}
              />
            </Field>
          </div>
          <div className="field-row">
            <Field label="Approved Date">
              <input type="date" value={draft.approval?.approved_date?.slice(0, 10) ?? ''}
                onChange={e => patchBlock('approval', 'approved_date', e.target.value || null)} />
            </Field>
          </div>
        </Section>

        {/* Review */}
        <Section title="Review" defaultOpen={false}>
          <div className="field-row">
            <Field label="Last Reviewed">
              <input type="date" value={draft.review?.last_reviewed?.slice(0, 10) ?? ''}
                onChange={e => patchBlock('review', 'last_reviewed', e.target.value || null)} />
            </Field>
          </div>
          <Field label="Reviewers" hint="from people list">
            <ControlledListEditor
              items={draft.review?.reviewers ?? []}
              onChange={v => patchBlock('review', 'reviewers', v)}
              vocabulary={enums?.owner || []}
              placeholder="Select reviewer..."
              allowFreeText={true}
            />
          </Field>
          <Field label="Review Note">
            <textarea value={draft.review?.note ?? ''} rows={2}
              onChange={e => patchBlock('review', 'note', e.target.value)} />
          </Field>
        </Section>

        {/* Implementation */}
        <Section title="Implementation" defaultOpen={false}>
          <div className="field-row">
            <Field label="Status"><EnumSelect value={draft.implementation?.status} options={enums?.implementation_status || []} onChange={v => patchBlock('implementation', 'status', v)} /></Field>
            <Field label="Branch">
              <input value={draft.implementation?.branch ?? ''} placeholder="feature/..."
                onChange={e => patchBlock('implementation', 'branch', e.target.value || null)} />
            </Field>
          </div>
        </Section>

        {/* History */}
        <Section title="History" defaultOpen={false}>
          <button className="btn btn-secondary" style={{ marginBottom: 8 }}
            onClick={async () => { if (!history) setHistory(await api.requirements.history(uid)); }}>
            Load history
          </button>
          {history && (
            <div className="history-list">
              {history.in_file?.map((h, i) => (
                <div key={i} className="history-item">
                  <span className="mono text-secondary" style={{ fontSize: 11 }}>v{h.version}</span>
                  <span className="history-date">{h.date?.slice(0, 10)}</span>
                  <span className="history-who">{h.modified_by}</span>
                  <span className="history-summary">{h.summary}</span>
                  {h.commit_sha && <span className="mono text-muted" style={{ fontSize: 10 }}>{h.commit_sha}</span>}
                  {h.change_ref && <span className="badge">{h.change_ref}</span>}
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* Attachments */}
        <Section title="Attachments" defaultOpen={false}>
          <AttachmentsSection uid={uid} />
        </Section>

        {/* Discussion */}
        <Section title="Discussion" defaultOpen={false}>
          <DiscussionSection uid={uid} currentUser={state.enums?._current_user || 'user'} />
        </Section>
      </div>

      {showCommit && (
        <CommitModal uid={uid} onCommit={handleCommit} onClose={() => setShowCommit(false)}
          changes={isDirty ? 'Unsaved changes will be saved automatically.' : 'No local changes.'} />
      )}
    </div>
  );
}
// Principle editor
// ---------------------------------------------------------------------------
function PrincipleEditor({ uid }) {
  const { state, toast } = useApp();
  const { enums } = state;
  const [draft, setDraft] = useState(null);
  const [req, setReq] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCommit, setShowCommit] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.principles.get(uid).then(d => { setDraft(d); setReq(d); }).catch(err => toast(err.message, 'error')).finally(() => setLoading(false));
  }, [uid]);

  const patch = (field, value) => setDraft(d => ({ ...d, [field]: value }));
  const patchContent = (field, value) => setDraft(d => ({ ...d, content: { ...d.content, [field]: value } }));
  const patchBlock = (block, field, value) => setDraft(d => ({ ...d, [block]: { ...d[block], [field]: value } }));

  const handleSave = async () => {
    try { const u = await api.principles.update(uid, draft); setReq(u); setDraft(u); toast('Saved', 'success'); }
    catch (err) { toast(err.message, 'error'); }
  };
  const handleCommit = async (message, increment, changeRef) => {
    try {
      if (JSON.stringify(draft) !== JSON.stringify(req)) await api.principles.update(uid, draft);
      const r = await api.principles.commit(uid, { message, increment, change_ref: changeRef });
      toast(`Committed: ${r.commit_sha?.slice(0, 7)}`, 'success');
      setShowCommit(false);
      dispatch({ type: 'COMMITTED' });
      const u = await api.principles.get(uid); setReq(u); setDraft(u);
    } catch (err) { toast(err.message, 'error'); }
  };

  if (loading) return <div className="editor-loading"><div className="spinner" /></div>;
  if (!draft) return null;
  const isDirty = JSON.stringify(draft) !== JSON.stringify(req);

  return (
    <div className="editor">
      <div className="editor-header">
        <div className="editor-header-left">
          <span className="editor-id mono">{draft.id}</span>
          <span className="editor-version mono text-muted">v{draft.version}</span>
          {isDirty && <span className="editor-dirty-badge">unsaved</span>}
        </div>
        <div className="editor-header-right">
          <button className="btn btn-secondary" onClick={handleSave} disabled={!isDirty}>Save</button>
          <button className="btn btn-primary" onClick={() => setShowCommit(true)}>Save &amp; Commit</button>
        </div>
      </div>
      <div className="editor-body">
        <Section title="Identity">
          <div className="field-row">
            <Field label="ID"><input value={draft.id ?? ''} onChange={e => patch('id', e.target.value)} /></Field>
            <Field label="Domain"><EnumSelect value={draft.domain} options={enums?.domain || []} onChange={v => patch('domain', v)} /></Field>
          </div>
          <Field label="Title"><input value={draft.title ?? ''} onChange={e => patch('title', e.target.value)} /></Field>
        </Section>
        <Section title="Content">
          <Field label="Principle Statement">
            <MarkdownEditor value={draft.content?.description} onChange={v => patchContent('description', v)} rows={4} />
          </Field>
          <Field label="Rationale">
            <MarkdownEditor value={draft.content?.rationale} onChange={v => patchContent('rationale', v)} rows={3} />
          </Field>
          <Field label="Implications">
            <MarkdownEditor value={draft.content?.implications} onChange={v => patchContent('implications', v)} rows={3} />
          </Field>
          <Field label="Exceptions">
            <textarea value={draft.content?.exceptions ?? ''} rows={2} onChange={e => patchContent('exceptions', e.target.value)} />
          </Field>
        </Section>
        <Section title="Links" defaultOpen={false}>
          <LinksEditor links={draft.links ?? []} onChange={v => patch('links', v)} enums={enums} />
        </Section>
        <Section title="Ownership & Status" defaultOpen={false}>
          <div className="field-row">
            <Field label="Owner"><input value={draft.owner ?? ''} onChange={e => patch('owner', e.target.value)} /></Field>
            <Field label="Approval Status"><EnumSelect value={draft.approval?.status} options={enums?.approval_status || []} onChange={v => patchBlock('approval', 'status', v)} /></Field>
          </div>
          <div className="field-row">
            <Field label="Approved By"><input value={draft.approval?.approved_by ?? ''} onChange={e => patchBlock('approval', 'approved_by', e.target.value || null)} /></Field>
          </div>
          <Field label="Tags" hint="from vocabulary"><ControlledListEditor items={draft.tags ?? []} onChange={v => patch('tags', v)} vocabulary={enums?.tags || []} placeholder="Select tag..." /></Field>
        </Section>

        <Section title="Attachments" defaultOpen={false}>
          <AttachmentsSection uid={uid} />
        </Section>
        <Section title="Discussion" defaultOpen={false}>
          <DiscussionSection uid={uid} currentUser={state.enums?._current_user || 'user'} />
        </Section>
      </div>
      {showCommit && <CommitModal uid={uid} onCommit={handleCommit} onClose={() => setShowCommit(false)} />}
    </div>
  );
}
function TBDEditor({ uid }) {
  const { state, toast } = useApp();
  const { enums } = state;
  const [draft, setDraft] = useState(null);
  const [req, setReq] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCommit, setShowCommit] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.tbds.get(uid).then(d => { setDraft(d); setReq(d); }).catch(err => toast(err.message, 'error')).finally(() => setLoading(false));
  }, [uid]);

  const patch = (field, value) => setDraft(d => ({ ...d, [field]: value }));
  const patchContent = (field, value) => setDraft(d => ({ ...d, content: { ...d.content, [field]: value } }));

  const handleSave = async () => {
    try { const u = await api.tbds.update(uid, draft); setReq(u); setDraft(u); toast('Saved', 'success'); }
    catch (err) { toast(err.message, 'error'); }
  };
  const handleCommit = async (message, increment, changeRef) => {
    try {
      if (JSON.stringify(draft) !== JSON.stringify(req)) await api.tbds.update(uid, draft);
      const r = await api.tbds.commit(uid, { message, increment, change_ref: changeRef });
      toast(`Committed: ${r.commit_sha?.slice(0, 7)}`, 'success');
      setShowCommit(false);
      dispatch({ type: 'COMMITTED' });
      const u = await api.tbds.get(uid); setReq(u); setDraft(u);
    } catch (err) { toast(err.message, 'error'); }
  };
  const handleResolve = async () => {
    const resolution = prompt('Resolution description:');
    if (!resolution) return;
    try {
      await api.tbds.resolve(uid, { resolution, resolved_by: 'user' });
      const u = await api.tbds.get(uid); setReq(u); setDraft(u);
      toast('TBD resolved', 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  if (loading) return <div className="editor-loading"><div className="spinner" /></div>;
  if (!draft) return null;
  const isDirty = JSON.stringify(draft) !== JSON.stringify(req);

  return (
    <div className="editor">
      <div className="editor-header">
        <div className="editor-header-left">
          <span className="editor-id mono">{draft.id}</span>
          <span className={`badge badge-${draft.status}`}>{draft.status}</span>
          {isDirty && <span className="editor-dirty-badge">unsaved</span>}
        </div>
        <div className="editor-header-right">
          {draft.status === 'open' && <button className="btn btn-secondary" onClick={handleResolve}>Resolve</button>}
          <button className="btn btn-secondary" onClick={handleSave} disabled={!isDirty}>Save</button>
          <button className="btn btn-primary" onClick={() => setShowCommit(true)}>Save &amp; Commit</button>
        </div>
      </div>
      <div className="editor-body">
        <Section title="Identity">
          <div className="field-row">
            <Field label="ID"><input value={draft.id ?? ''} onChange={e => patch('id', e.target.value)} /></Field>
            <Field label="Status"><EnumSelect value={draft.status} options={enums?.tbd_status || []} onChange={v => patch('status', v)} nullable={false} /></Field>
          </div>
          <Field label="Title"><input value={draft.title ?? ''} onChange={e => patch('title', e.target.value)} /></Field>
        </Section>
        <Section title="Content">
          <Field label="Description"><MarkdownEditor value={draft.content?.description} onChange={v => patchContent('description', v)} rows={4} /></Field>
          <Field label="Impact"><MarkdownEditor value={draft.content?.impact} onChange={v => patchContent('impact', v)} rows={3} /></Field>
          <Field label="Resolution Criteria"><MarkdownEditor value={draft.content?.resolution_criteria} onChange={v => patchContent('resolution_criteria', v)} rows={3} /></Field>
          {(draft.content?.resolution || draft.status === 'resolved') && (
            <Field label="Resolution"><textarea value={draft.content?.resolution ?? ''} rows={2} onChange={e => patchContent('resolution', e.target.value)} /></Field>
          )}
        </Section>
        <Section title="Ownership" defaultOpen={false}>
          <div className="field-row">
            <Field label="Owner"><input value={draft.owner ?? ''} onChange={e => patch('owner', e.target.value || null)} /></Field>
            <Field label="Due"><input value={draft.due ?? ''} onChange={e => patch('due', e.target.value || null)} /></Field>
          </div>
          <div className="field-row">
            <Field label="Priority"><EnumSelect value={draft.priority} options={enums?.priority || []} onChange={v => patch('priority', v)} /></Field>
          </div>
          <Field label="Tags" hint="from vocabulary"><ControlledListEditor items={draft.tags ?? []} onChange={v => patch('tags', v)} vocabulary={enums?.tags || []} placeholder="Select tag..." /></Field>
        </Section>
        <Section title="Links" defaultOpen={false}>
          <LinksEditor links={draft.links ?? []} onChange={v => patch('links', v)} enums={enums} />
        </Section>
        {draft.affected_requirements?.length > 0 && (
          <Section title="Affected Requirements" defaultOpen={false}>
            <div className="history-list">
              {draft.affected_requirements.map(u => (
                <div key={u} className="history-item mono text-secondary" style={{ fontSize: 11 }}>{u}</div>
              ))}
            </div>
          </Section>
        )}
        <Section title="Attachments" defaultOpen={false}>
          <AttachmentsSection uid={uid} />
        </Section>
        <Section title="Discussion" defaultOpen={false}>
          <DiscussionSection uid={uid} currentUser={state.enums?._current_user || 'user'} />
        </Section>
      </div>
      {showCommit && <CommitModal uid={uid} onCommit={handleCommit} onClose={() => setShowCommit(false)} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
function EditorEmpty() {
  return (
    <div className="editor-empty">
      <div className="editor-empty-icon">◈</div>
      <div className="editor-empty-text">Select an item from the tree to view or edit it.</div>
    </div>
  );
}

export default function Editor() {
  const { state } = useApp();
  const { selectedUid, selectedType } = state;
  if (!selectedUid) return <EditorEmpty />;
  if (selectedType === 'requirement') return <RequirementEditor uid={selectedUid} />;
  if (selectedType === 'principle')   return <PrincipleEditor uid={selectedUid} />;
  if (selectedType === 'tbd')         return <TBDEditor uid={selectedUid} />;
  return <EditorEmpty />;
}
