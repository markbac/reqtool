import { useEffect, useState } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';
import { Panel } from './Advanced/Panel';
import './Workflow.css';

const SEVERITY_ORDER = { error: 0, warning: 1, info: 2 };

function IssueLine({ issue, showItem, onOpen }) {
  return (
    <li className={`wc-issue wc-issue--${issue.severity}`}>
      <span className="wc-rule mono">{issue.rule}</span>
      {showItem && <button className="btn btn-ghost wc-item" onClick={() => onOpen(issue.uid)}>{issue.id}</button>}
      <span className="wc-where text-muted">{issue.field}:{issue.line}</span>
      <span className="wc-msg">{issue.message}{issue.suggestion ? <em> -- {issue.suggestion}</em> : null}</span>
    </li>
  );
}

/** A one-line summary under the item header: how many writing findings this item has, expandable to the list. */
export function WritingStrip({ uid, version }) {
  const [result, setResult] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let live = true;
    api.requirements.lint(uid).then(r => { if (live) setResult(r); }).catch(() => { if (live) setResult(null); });
    return () => { live = false; };
  }, [uid, version]);

  if (!result || !result.enabled || !result.issues?.length) return null;
  const issues = [...result.issues].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
  return (
    <div className="wc-strip" data-testid="writing-strip">
      <button className="btn btn-ghost" onClick={() => setOpen(o => !o)} aria-expanded={open}>
        ✎ {issues.length} writing {issues.length === 1 ? 'suggestion' : 'suggestions'} {open ? '▾' : '▸'}
      </button>
      {open && <ul className="wc-list">{issues.map((i, n) => <IssueLine key={n} issue={i} />)}</ul>}
    </div>
  );
}

const lines = (v) => (v || []).join('\n');
const fromLines = (t) => t.split('\n').map(x => x.trim()).filter(Boolean);
const glossaryText = (g) => Object.entries(g || {}).map(([k, v]) => `${k}: ${(v || []).join(', ')}`).join('\n');
const glossaryFrom = (t) => Object.fromEntries(fromLines(t).map(l => {
  const [k, ...rest] = l.split(':');
  return [k.trim(), rest.join(':').split(',').map(x => x.trim()).filter(Boolean)];
}).filter(([k]) => k));
const phrasesText = (p) => Object.entries(p || {}).map(([k, v]) => `${k} => ${v}`).join('\n');
const phrasesFrom = (t) => Object.fromEntries(fromLines(t).map(l => {
  const [k, ...rest] = l.split('=>');
  return [k.trim(), rest.join('=>').trim()];
}).filter(([k]) => k));

function Row({ label, hint, children }) {
  return (
    <label className="wc-row">
      <span className="wc-row-label">{label}{hint && <span className="text-muted"> {hint}</span>}</span>
      {children}
    </label>
  );
}

function Settings({ info, editable, onSaved }) {
  const { toast } = useApp();
  const [s, setS] = useState(info.settings);
  const [saving, setSaving] = useState(false);
  const set = (key, value) => setS(cur => ({ ...cur, [key]: value }));
  const setVale = (key, value) => setS(cur => ({ ...cur, vale: { ...cur.vale, [key]: value } }));
  const lock = !editable;

  const save = async () => {
    setSaving(true);
    try { onSaved(await api.lint.saveConfig(s)); toast('Writing check settings saved', 'success'); }
    catch (err) { toast(err.message, 'error', 6000); }
    finally { setSaving(false); }
  };

  const vale = info.vale || {};
  return (
    <div className="wc-settings">
      <div className="import-hint">
        These settings are stored in <code>{info.file}</code> in the repository. Every setting is listed there, so you
        can also edit the file directly.
      </div>
      {info.problems?.length > 0 && <div className="td-problem" role="alert">{info.problems.join('; ')}</div>}
      <fieldset disabled={lock} className="wc-fieldset">
        <Row label="Writing check enabled"><input type="checkbox" checked={!!s.enabled} onChange={e => set('enabled', e.target.checked)} /></Row>
        <Row label="Include in validation" hint="(req validate and the Validate panel)">
          <input type="checkbox" checked={!!s.include_in_validation} onChange={e => set('include_in_validation', e.target.checked)} />
        </Row>

        <div className="metrics-section-title">Rules</div>
        {info.rules.map(rule => {
          const off = (s.disabled_rules || []).includes(rule.id);
          return (
            <div key={rule.id} className="wc-rule-row">
              <input type="checkbox" aria-label={`Enable ${rule.id}`} checked={!off}
                onChange={e => set('disabled_rules', e.target.checked ? s.disabled_rules.filter(r => r !== rule.id) : [...s.disabled_rules, rule.id])} />
              <span className="mono wc-rule">{rule.id}</span>
              <span className="wc-msg">{rule.description}</span>
              <select aria-label={`Severity of ${rule.id}`} value={s.severities?.[rule.id] || 'warning'}
                onChange={e => set('severities', { ...s.severities, [rule.id]: e.target.value })}>
                <option value="error">error</option><option value="warning">warning</option><option value="info">info</option>
              </select>
            </div>
          );
        })}

        <div className="metrics-section-title">What is checked</div>
        <Row label="Fields" hint="(one per line)">
          <textarea rows={3} value={lines(s.fields)} onChange={e => set('fields', fromLines(e.target.value))} />
        </Row>
        <Row label="Item types REQ002 applies to" hint="(one per line, empty means all)">
          <textarea rows={2} value={lines(s.statement_types)} onChange={e => set('statement_types', fromLines(e.target.value))} />
        </Row>
        <Row label="Glossary" hint="(Correct: wrong, wrong)">
          <textarea rows={6} value={glossaryText(s.glossary)} onChange={e => set('glossary', glossaryFrom(e.target.value))} />
        </Row>
        <Row label="Wordy phrases" hint="(phrase => better wording)">
          <textarea rows={5} value={phrasesText(s.redundant_phrases)} onChange={e => set('redundant_phrases', phrasesFrom(e.target.value))} />
        </Row>
        <Row label="Vague terms" hint="(one per line)">
          <textarea rows={5} value={lines(s.vague_terms)} onChange={e => set('vague_terms', fromLines(e.target.value))} />
        </Row>
        <Row label="Acronyms that need no definition" hint="(one per line)">
          <textarea rows={4} value={lines(s.allowed_acronyms)} onChange={e => set('allowed_acronyms', fromLines(e.target.value))} />
        </Row>
        <Row label="Shortest acronym checked">
          <input type="number" min={2} value={s.acronym_min_length} onChange={e => set('acronym_min_length', Number(e.target.value))} />
        </Row>

        <div className="metrics-section-title">Vale</div>
        <div className="wc-vale-status" data-testid="vale-status">
          {vale.available ? `Vale found${vale.version ? ` (${vale.version})` : ''}` : 'Vale was not found on this machine. Run `req tools` on the server to install it.'}
          {vale.message ? ` ${vale.message}` : ''}
        </div>
        <Row label="Use Vale"><input type="checkbox" checked={!!s.vale.enabled} onChange={e => setVale('enabled', e.target.checked)} /></Row>
        <Row label="Vale command"><input value={s.vale.binary || ''} onChange={e => setVale('binary', e.target.value)} /></Row>
        <Row label="Your own .vale.ini" hint="(empty: reqtool writes one from the settings below)">
          <input value={s.vale.config_file || ''} onChange={e => setVale('config_file', e.target.value || null)} />
        </Row>
        <Row label="Styles folder" hint="(empty: .reqtool/vale/styles)">
          <input value={s.vale.styles_path || ''} onChange={e => setVale('styles_path', e.target.value || null)} />
        </Row>
        <Row label="Styles" hint="(one per line)">
          <textarea rows={2} value={lines(s.vale.styles)} onChange={e => setVale('styles', fromLines(e.target.value))} />
        </Row>
        <Row label="Checks to turn off" hint="(one per line, Style.Check)">
          <textarea rows={2} value={lines(s.vale.disabled_checks)} onChange={e => setVale('disabled_checks', fromLines(e.target.value))} />
        </Row>
        <Row label="Lowest level reported">
          <select value={s.vale.min_alert_level} onChange={e => setVale('min_alert_level', e.target.value)}>
            <option value="suggestion">suggestion</option><option value="warning">warning</option><option value="error">error</option>
          </select>
        </Row>
        <Row label="Time limit (seconds)">
          <input type="number" min={1} value={s.vale.timeout_seconds} onChange={e => setVale('timeout_seconds', Number(e.target.value))} />
        </Row>
        <Row label="Include Vale in validation"><input type="checkbox" checked={!!s.vale.include_in_validation} onChange={e => setVale('include_in_validation', e.target.checked)} /></Row>
      </fieldset>
      {editable ? (
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? <span className="spinner" /> : 'Save settings'}</button>
          <button className="btn btn-secondary" onClick={() => setS(info.defaults)}>Reset to defaults</button>
        </div>
      ) : <div className="text-muted" style={{ marginTop: 8, fontSize: 11 }}>Only an administrator can change these settings.</div>}
    </div>
  );
}

/** Repository-wide writing results, and (for administrators) the settings that drive them. */
export function WritingCheckPanel({ onClose }) {
  const { dispatch } = useApp();
  const can = useCan();
  const [tab, setTab] = useState('results');
  const [report, setReport] = useState(null);
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);

  const run = () => { setReport(null); api.lint.all().then(setReport).catch(e => setError(e.message)); };
  useEffect(() => { run(); api.lint.config().then(setInfo).catch(e => setError(e.message)); }, []);

  const open = (uid) => { dispatch({ type: 'SELECT', uid, artefactType: 'requirement' }); onClose(); };
  const saved = (next) => { setInfo(next); run(); };

  return (
    <Panel title="Writing check" onClose={onClose} width={640}>
      <div className="editor-tabs">
        {[['results', 'Results'], ['settings', can('manage_lint') ? 'Settings' : 'Settings (read only)']].map(([id, label]) => (
          <button key={id} className={`editor-tab ${tab === id ? 'editor-tab--active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>
      {error && <div className="td-problem" role="alert">{error}</div>}
      {tab === 'results' && (!report ? <div className="panel-loading"><div className="spinner" /></div> : (
        <div>
          {!report.enabled && <div className="import-hint">The writing check is turned off in the settings.</div>}
          <div className="wc-summary" data-testid="wc-summary">
            {report.summary.issues} finding(s) in {report.summary.items_with_issues} of {report.summary.items} item(s)
            {' -- '}{report.summary.by_severity.error} error, {report.summary.by_severity.warning} warning, {report.summary.by_severity.info} info
            <button className="btn btn-ghost" onClick={run} style={{ marginLeft: 8 }}>Re-run</button>
          </div>
          <ul className="wc-list">{report.issues.map((i, n) => <IssueLine key={n} issue={i} showItem onOpen={open} />)}</ul>
          {report.truncated && <div className="text-muted">Only the first {report.issues.length} findings are shown.</div>}
        </div>
      ))}
      {tab === 'settings' && (info ? <Settings info={info} editable={can('manage_lint')} onSaved={saved} /> : <div className="panel-loading"><div className="spinner" /></div>)}
    </Panel>
  );
}
