import { useState, useEffect, useRef } from 'react';
import { api } from '../../api';
import { useCan } from '../../AppContext';

// Pages Ctrl+K can open, besides items (#373).
const PAGES = [
  ['requirements', 'tree', 'Requirements: tree'], ['requirements', 'table', 'Requirements: query and saved views'],
  ['requirements', 'modules', 'Requirements: modules'], ['requirements', 'baselines', 'Requirements: baselines'],
  ['requirements', 'changesets', 'Requirements: change sets'], ['requirements', 'writing', 'Requirements: writing check'],
  ['requirements', 'duplicates', 'Requirements: duplicates'],
  ['work', 'issues', 'Work: issues'], ['work', 'backlog', 'Work: backlog'], ['work', 'tree', 'Work: tree'], ['work', 'board', 'Work: board'],
  ['work', 'roadmap', 'Work: roadmap'], ['work', 'iterations', 'Work: iterations and gates'],
  ['decisions', '', 'Decisions'], ['decisions', 'records', 'Decisions: options, ATAM and ADR export'], ['principles', 'library', 'Principles'], ['principles', 'cited', 'Principles: where cited'],
  ['insights', 'overview', 'Insights: overview, release gate and metrics'], ['insights', 'coverage', 'Insights: coverage'],
  ['insights', 'traceability', 'Insights: traceability'], ['insights', 'views', 'Insights: views'],
  ['insights', 'diagrams', 'Insights: diagrams'],
  ['settings', 'workflows', 'Settings: workflows'], ['settings', 'fields', 'Settings: custom fields', 'manage_config'],
  ['settings', 'vocabularies', 'Settings: vocabularies', 'manage_config'], ['settings', 'templates', 'Settings: templates', 'manage_config'],
  ['settings', 'automation', 'Settings: automation rules'], ['settings', 'webhooks', 'Settings: webhooks', 'manage_webhooks'],
  ['settings', 'writing', 'Settings: writing check'], ['settings', 'repository', 'Settings: repository', 'manage_repo'],
];

export function CmdPalette({ onClose, onSelect, onNavigate }) {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef(null);
  const can = useCan();

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    if (!query.trim()) { setItems([]); return; }
    const t = setTimeout(() => {
      api.search(query, 30).then(r => { setItems(r); setSelected(0); }).catch(() => {});
    }, 150);
    return () => clearTimeout(t);
  }, [query]);

  const q = query.trim().toLowerCase();
  // a settings page the role may not use is left out, as on the Settings page
  const pages = onNavigate && q
    ? PAGES.filter(([, , label, need]) => (!need || can(need)) && label.toLowerCase().includes(q)).slice(0, 6) : [];
  const results = [...pages.map(([area, tab, label]) => ({ page: true, area, tab, label, key: `${area}/${tab}` })),
    ...items.map(r => ({ ...r, key: r.uid }))];

  const choose = (r) => (r.page ? onNavigate(r.area, r.tab) : onSelect(r.uid, r.type));
  const handleKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, results.length - 1)); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
    if (e.key === 'Enter' && results[selected]) choose(results[selected]);
    if (e.key === 'Escape') onClose();
  };

  const TYPE_LABELS = { requirement: 'REQ', principle: 'P', decision: 'DEC', tbd: 'DEC' };

  return (
    <div className="cmdpalette-overlay" onClick={onClose}>
      <div className="cmdpalette" role="dialog" aria-label="Search" onClick={e => e.stopPropagation()}>
        <div className="cmdpalette-search">
          <span className="cmdpalette-icon" aria-hidden="true">⌕</span>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            aria-label="Search items, decisions and pages"
            placeholder="Search requirements, work items, principles, decisions and pages..."
            className="cmdpalette-input"
          />
          <span className="cmdpalette-hint">↑↓ navigate · Enter select · Esc close</span>
        </div>
        {results.length > 0 && (
          <div className="cmdpalette-results" role="listbox">
            {results.map((r, i) => (
              <div
                key={r.key}
                role="option"
                aria-selected={i === selected}
                className={`cmdpalette-result ${i === selected ? 'cmdpalette-result--selected' : ''}`}
                onMouseEnter={() => setSelected(i)}
                onClick={() => choose(r)}
              >
                <span className="cmdpalette-type-badge">{r.page ? 'Page' : (TYPE_LABELS[r.type] || r.type)}</span>
                {!r.page && <span className="cmdpalette-id mono">{r.id}</span>}
                <span className="cmdpalette-title">{r.page ? r.label : r.title}</span>
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
