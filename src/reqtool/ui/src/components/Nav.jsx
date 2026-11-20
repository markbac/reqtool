/**
 * Nav.jsx -- The left-hand menu (#373): six areas, each a page with its own address. Collapses to icons
 * (remembered), and below 900 px wide opens as an overlay from the header's menu button (#376).
 */

import { useEffect, useState } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import './Nav.css';

const ICONS = {
  requirements: <path d="M6 3h9l4 4v14H6z M14 3v5h5 M9 13h7 M9 17h7" />,
  work: <><rect x="3" y="4" width="5" height="16" rx="1" /><rect x="10" y="4" width="5" height="11" rx="1" /><rect x="17" y="4" width="4" height="7" rx="1" /></>,
  decisions: <path d="M12 3v18 M5 7h14 M5 7l-3 7h6z M19 7l-3 7h6z" />,
  principles: <path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z M4 19V5" />,
  insights: <path d="M4 20V10 M10 20V4 M16 20v-7 M22 20H2" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1L7 17 M17 7l2.1-2.1" /></>,
  collapse: <path d="M15 6l-6 6 6 6" />,
};

export function Icon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
  );
}

const MAIN = [
  { area: 'requirements', label: 'Requirements' },
  { area: 'work', label: 'Work', badge: 'triage' },
  { area: 'decisions', label: 'Decisions', badge: 'pending' },
  { area: 'principles', label: 'Principles' },
  { area: 'insights', label: 'Insights' },
];

const COLLAPSED_KEY = 'reqtool:nav-collapsed';

function readCollapsed() {
  try { return localStorage.getItem(COLLAPSED_KEY) === '1'; } catch { return false; }
}

/** Counts for the menu badges: issues waiting for triage, decisions still pending. */
function useBadges() {
  const { state } = useApp();
  const [counts, setCounts] = useState({ triage: 0, pending: 0 });
  useEffect(() => {
    let live = true;
    Promise.all([
      api.decisions.list({ status: 'proposed' }).catch(() => []),
      api.requirements.list({ req_type: 'issue' }).catch(() => []),
    ]).then(([pending, issues]) => {
      if (!live) return;
      const items = Array.isArray(issues) ? issues : (issues?.items || []);
      setCounts({
        pending: Array.isArray(pending) ? pending.length : 0,
        triage: items.filter(i => i.req_type === 'issue' && ['reported', 'in_triage'].includes(i.status)).length,
      });
    });
    return () => { live = false; };
  }, [state._lastCommit]);
  return counts;
}

export default function Nav({ open, onClose }) {
  const { state, dispatch } = useApp();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const badges = useBadges();

  const toggle = () => {
    setCollapsed(c => {
      try { localStorage.setItem(COLLAPSED_KEY, c ? '0' : '1'); } catch { /* not remembered */ }
      return !c;
    });
  };
  const go = (area) => { dispatch({ type: 'NAVIGATE', area }); onClose?.(); };

  const item = ({ area, label, badge }) => {
    const count = badge ? badges[badge] : 0;
    const current = state.area === area;
    return (
      <a key={area} href={`#/${area}`} className={`nav-item ${current ? 'nav-item--on' : ''}`}
        aria-current={current ? 'page' : undefined} title={collapsed ? label : undefined}
        onClick={e => { e.preventDefault(); go(area); }}>
        <Icon name={area} />
        <span className="nav-label">{label}</span>
        {count > 0 && (
          <span className={`nav-badge nav-badge--${badge}`}
            aria-label={badge === 'triage' ? `${count} issues to triage` : `${count} pending decisions`}>{count}</span>
        )}
      </a>
    );
  };

  return (
    <>
      {open && <div className="nav-backdrop" onClick={onClose} aria-hidden="true" />}
      <nav aria-label="Main" className={`nav ${collapsed ? 'nav--collapsed' : ''} ${open ? 'nav--open' : ''}`}>
        {MAIN.map(item)}
        <div className="nav-spacer" />
        {item({ area: 'settings', label: 'Settings' })}
        <button className="nav-item nav-collapse" onClick={toggle} aria-expanded={!collapsed}
          title={collapsed ? 'Expand menu' : 'Collapse menu'}>
          <Icon name="collapse" />
          <span className="nav-label">Collapse menu</span>
        </button>
      </nav>
    </>
  );
}
