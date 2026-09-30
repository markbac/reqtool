import { useState, useEffect, useRef } from 'react';
import { api } from '../../api';

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
