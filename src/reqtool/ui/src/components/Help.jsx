/**
 * Help.jsx
 * Three panels exposed via the ? button and keyboard shortcut:
 *   - About: version, repo info, quick-start guide
 *   - Help: contextual help topics (loaded from GET /help)
 *   - Templates: browse and apply requirement templates
 */

import { useState, useEffect } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import './Help.css';

// ---------------------------------------------------------------------------
// About tab
// ---------------------------------------------------------------------------
function AboutTab() {
  const { state } = useApp();
  const product = state.activeProduct;
  const reqCount = 0; // shown from header context

  return (
    <div className="help-about">
      <div className="help-about-brand">
        <span className="help-brand-icon">◈</span>
        <div>
          <div className="help-brand-name">reqtool</div>
          <div className="help-brand-tagline">Git-backed requirements management</div>
        </div>
      </div>

      <div className="help-section">
        <h3>What is reqtool?</h3>
        <p>
          reqtool stores requirements, principles, and TBDs as individual YAML files in a git
          repository. Every artefact has a unique ID, a content hash, and a full version history.
          The tool handles validation, workflow enforcement, traceability, and export automatically.
        </p>
        <p>
          Because requirements are plain files, they work with your existing git workflow -- branch,
          review, merge, tag -- and every change is traceable to a commit.
        </p>
      </div>

      <div className="help-section">
        <h3>Quick start</h3>
        <ol className="help-steps">
          <li>
            <strong>Select or create a product</strong> using the dropdown in the top bar.
            Products group requirements into a deliverable.
          </li>
          <li>
            <strong>Add requirements</strong> using the <kbd>+ New</kbd> button in the sidebar,
            or pick a template from the Templates tab to pre-fill common fields.
          </li>
          <li>
            <strong>Structure your tree</strong> by setting the Parent Requirement field.
            Systems: Stakeholder Need → Functional → Derived.
            Agile: Theme → Epic → Feature → Story → Task.
          </li>
          <li>
            <strong>Work items</strong> live in Task Mgmt. Systems requirements live in Requirements.
            Link them with a <em>satisfies</em> relationship.
          </li>
          <li>
            <strong>Commit</strong> using Save &amp; Commit or the staged-files badge in the header.
            Each commit writes a git commit so you have a full audit trail.
          </li>
          <li>
            <strong>Validate</strong> with ✓ Validate to check all requirements pass business rules.
          </li>
        </ol>
      </div>

      <div className="help-section">
        <h3>Keyboard shortcuts</h3>
        <table className="help-shortcuts">
          <tbody>
            <tr><td><kbd>Ctrl+K</kbd></td><td>Global search / command palette</td></tr>
            <tr><td><kbd>Ctrl+S</kbd></td><td>Save current requirement</td></tr>
            <tr><td><kbd>?</kbd></td><td>Open this help panel</td></tr>
            <tr><td><kbd>Esc</kbd></td><td>Close any overlay</td></tr>
          </tbody>
        </table>
      </div>

      <div className="help-section">
        <h3>Two vocabularies</h3>
        <div className="help-grid">
          <div className="help-card">
            <div className="help-card-title">Systems engineering</div>
            <div className="help-card-types">
              <span>👤 Stakeholder Need</span>
              <span>⚙️ Functional</span>
              <span>📈 Performance</span>
              <span>🔒 Security</span>
              <span>⚠️ Safety</span>
              <span>🔌 Interface</span>
              <span>📋 Compliance</span>
              <span>🚧 Constraint</span>
            </div>
            <div className="help-card-workflow">Workflow: draft → in_review → reviewed → approved</div>
          </div>
          <div className="help-card">
            <div className="help-card-title">Agile planning</div>
            <div className="help-card-types">
              <span>🎯 Theme</span>
              <span>🚀 Initiative</span>
              <span>📦 Epic</span>
              <span>✨ Feature</span>
              <span>📖 Story</span>
              <span>✅ Task</span>
              <span>🐛 Bug</span>
              <span>🔬 Spike</span>
            </div>
            <div className="help-card-workflow">Workflow: backlog → ready → in_progress → done</div>
          </div>
        </div>
      </div>

      <div className="help-footer">
        <a href="/docs" target="_blank" rel="noreferrer">API docs (Swagger) ↗</a>
        <a href="/redoc" target="_blank" rel="noreferrer">ReDoc ↗</a>
        <a href="/badge/validated" target="_blank" rel="noreferrer">CI badge ↗</a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Help topics tab
// ---------------------------------------------------------------------------
const TOPICS = [
  { id: 'concepts',     label: 'Concepts' },
  { id: 'fields',       label: 'Fields' },
  { id: 'workflow',     label: 'Workflow' },
  { id: 'relationships',label: 'Relationships' },
  { id: 'estimates',    label: 'Estimates' },
  { id: 'dor_dod',      label: 'DoR / DoD' },
  { id: 'validation',   label: 'Validation' },
  { id: 'git_baselines',label: 'Git & Baselines' },
  { id: 'export',       label: 'Export' },
];

function HelpTab() {
  const [activeTopic, setActiveTopic] = useState('concepts');
  const [content, setContent] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.help.get(activeTopic)
      .then(data => setContent(data))
      .catch(() => setContent({ overview: 'Could not load help content.' }))
      .finally(() => setLoading(false));
  }, [activeTopic]);

  const renderMarkdown = (text) => {
    if (!text) return null;
    // Very simple inline markdown for help content
    const html = text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/^##\s+(.+)$/gm, '<h4>$1</h4>')
      .replace(/^-\s+(.+)$/gm, '<li>$1</li>');
    return { __html: `<p>${html}</p>` };
  };

  return (
    <div className="help-topics">
      <nav className="help-topic-nav">
        {TOPICS.map(t => (
          <button key={t.id}
            className={`help-topic-btn ${activeTopic === t.id ? 'help-topic-btn--active' : ''}`}
            onClick={() => setActiveTopic(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      <div className="help-topic-content">
        {loading && <div className="help-loading">Loading…</div>}
        {!loading && Object.entries(content).map(([key, value]) => (
          <div key={key} className="help-topic-section">
            <h4 className="help-topic-heading">{key.replace(/_/g, ' ')}</h4>
            <div className="help-topic-body" dangerouslySetInnerHTML={renderMarkdown(value)} />
          </div>
        ))}
        {!loading && Object.keys(content).length === 0 && (
          <div className="help-empty">No content for this topic.</div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Templates tab
// ---------------------------------------------------------------------------
function TemplatesTab({ onApply }) {
  const { state } = useApp();
  const templates = state.templates || [];
  const [selected, setSelected] = useState(null);

  const AGILE_TEMPLATES = [
    { id: '_story',      label: 'User Story',    description: 'Unit of user value. As a [user], I want [goal] so that [benefit].', icon: '📖',
      fields: { req_type: 'story', priority: 'medium', content: { description: 'As a [user], I want [goal] so that [benefit].', rationale: '' } } },
    { id: '_task',       label: 'Task',          description: 'Concrete technical work item.', icon: '✅',
      fields: { req_type: 'task', priority: 'medium', content: { description: 'Implement [component/behaviour] to support [goal].', rationale: '' } } },
    { id: '_bug',        label: 'Bug',           description: 'Defect with steps to reproduce.', icon: '🐛',
      fields: { req_type: 'bug', priority: 'high', content: { description: 'Steps to reproduce:\n1. \n\nExpected: \nActual: ', rationale: '' } } },
    { id: '_spike',      label: 'Spike',         description: 'Time-boxed investigation.', icon: '🔬',
      fields: { req_type: 'spike', priority: 'medium', content: { description: 'Question: [what are we trying to learn?]\nTime-box: [N] points\nOutput: [decision/prototype/report]', rationale: '' } } },
    { id: '_epic',       label: 'Epic',          description: 'Significant user-facing capability.', icon: '📦',
      fields: { req_type: 'epic', priority: 'high', content: { description: '[Capability] to enable [user/business outcome].', rationale: '' } } },
  ];

  const allTemplates = [
    { _group: 'Agile', items: AGILE_TEMPLATES },
    { _group: 'Systems Engineering', items: templates },
  ];

  return (
    <div className="help-templates">
      <div className="help-templates-hint">
        Select a template, then click <strong>Use template</strong> to create a new requirement
        with fields pre-filled. Edit <code>.reqtool/templates.yaml</code> to add your own.
      </div>

      {allTemplates.map(group => (
        <div key={group._group} className="help-template-group">
          <div className="help-template-group-label">{group._group}</div>
          {group.items.length === 0 && (
            <div className="help-empty">No templates. Add them to <code>.reqtool/templates.yaml</code>.</div>
          )}
          {group.items.map(t => (
            <div key={t.id}
              className={`help-template-item ${selected?.id === t.id ? 'help-template-item--selected' : ''}`}
              onClick={() => setSelected(selected?.id === t.id ? null : t)}>
              <div className="help-template-header">
                <span className="help-template-icon">{t.icon || '◈'}</span>
                <div className="help-template-meta">
                  <span className="help-template-label">{t.label}</span>
                  {t.description && <span className="help-template-desc">{t.description}</span>}
                </div>
                <button className="btn btn-primary help-template-use"
                  style={{ fontSize: 11, padding: '4px 12px', flexShrink: 0 }}
                  onClick={e => { e.stopPropagation(); onApply(t); }}>
                  Use template
                </button>
              </div>
              {selected?.id === t.id && t.fields && (
                <div className="help-template-preview">
                  {Object.entries(t.fields).map(([k, v]) => (
                    <div key={k} className="help-template-field-row">
                      <span className="mono" style={{ fontSize: 10, color: 'var(--text-muted)', minWidth: 120 }}>{k}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                        {typeof v === 'object' ? JSON.stringify(v).slice(0, 80) : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HelpPanel -- the outer shell with tabs
// ---------------------------------------------------------------------------
export function HelpPanel({ onClose, initialTab = 'about', onApplyTemplate }) {
  const [tab, setTab] = useState(initialTab);

  const TABS = [
    { id: 'about',     label: '◈ About' },
    { id: 'help',      label: '? Help'  },
    { id: 'templates', label: '◫ Templates' },
  ];

  return (
    <div className="help-overlay" onClick={onClose}>
      <div className="help-panel" onClick={e => e.stopPropagation()}>
        <div className="help-panel-header">
          <div className="help-panel-tabs">
            {TABS.map(t => (
              <button key={t.id}
                className={`help-panel-tab ${tab === t.id ? 'help-panel-tab--active' : ''}`}
                onClick={() => setTab(t.id)}>
                {t.label}
              </button>
            ))}
          </div>
          <button className="btn btn-ghost" style={{ fontSize: 14, padding: '4px 8px' }}
            onClick={onClose}>✕</button>
        </div>
        <div className="help-panel-body">
          {tab === 'about'     && <AboutTab />}
          {tab === 'help'      && <HelpTab />}
          {tab === 'templates' && <TemplatesTab onApply={t => { onApplyTemplate?.(t); onClose(); }} />}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline help tooltip -- shown next to field labels
// ---------------------------------------------------------------------------
const FIELD_HELP = {
  'ID':          'Human-readable identifier. Auto-assigned from the type prefix (e.g. US-042). Unique in the repository.',
  'Status':      'Current workflow state. Valid transitions depend on the item type. Sprint types start at Backlog.',
  'Priority':    'Critical = must-have / safety-related. High = important for launch. Medium = default. Low = nice-to-have.',
  'Type':        'The item type determines which workflow, ID prefix, and DoR/DoD apply.',
  'Domain':      'The system or product domain this requirement belongs to (e.g. comms, security, ux).',
  'Owner':       'The person accountable for this requirement (not necessarily doing the work).',
  'Assignee':    'The person currently doing the work. Distinct from Owner.',
  'Iteration':   'Sprint name, PI, or milestone. Plain text e.g. Sprint-3 or PI-2.',
  'Estimate':    'Numeric effort estimate. Unit is set per-repo in enums.yaml (default: points).',
  'Rationale':   'Why this requirement exists. Required for approved formal requirements. Answers "why" not "what".',
  'Relationships': 'Links to other requirements. Use satisfies/implements to connect agile items to systems requirements.',
};

export function FieldHelp({ field }) {
  const [visible, setVisible] = useState(false);
  const help = FIELD_HELP[field];
  if (!help) return null;
  return (
    <span className="field-help-trigger" onMouseEnter={() => setVisible(true)} onMouseLeave={() => setVisible(false)}>
      ?
      {visible && <span className="field-help-tooltip">{help}</span>}
    </span>
  );
}
