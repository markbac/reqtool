/**
 * Kanban.jsx -- Full-width kanban board for Task Management.
 * Rendered in <main> (not the sidebar) so it uses the full window width.
 * Columns = workflow states. Swimlanes = by person (assignee) or by team (owner).
 */

import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import './Kanban.css';

const TYPE_META = {
  theme:      { icon: '🎯', colour: '#6e40c9', label: 'Theme' },
  initiative: { icon: '🚀', colour: '#1f6feb', label: 'Initiative' },
  epic:       { icon: '📦', colour: '#388bfd', label: 'Epic' },
  feature:    { icon: '✨', colour: '#56d364', label: 'Feature' },
  story:      { icon: '📖', colour: '#79c0ff', label: 'Story' },
  task:       { icon: '✅', colour: '#d2a8ff', label: 'Task' },
  bug:        { icon: '🐛', colour: '#ff7b72', label: 'Bug' },
  spike:      { icon: '🔬', colour: '#ffa657', label: 'Spike' },
};

const AGILE_TYPES = ['theme', 'initiative', 'epic', 'feature', 'story', 'task', 'bug', 'spike'];

const KANBAN_GROUPINGS = [
  { id: 'assignee', label: 'By Person' },
  { id: 'owner',    label: 'By Team'   },
  { id: 'none',     label: 'All'       },
];

function KanbanCard({ card, isSelected, onClick }) {
  const meta = TYPE_META[card.req_type] || {};
  return (
    <div className={`kanban-card ${isSelected ? 'kanban-card--selected' : ''}`}
      style={{ borderLeft: `3px solid ${meta.colour || 'var(--border)'}` }}
      onClick={onClick} title={card.title}>
      <div className="kanban-card-header">
        <span className="kanban-card-id mono">{card.id}</span>
        {meta.icon && <span className="kanban-card-icon">{meta.icon}</span>}
        {card.estimate != null && <span className="kanban-card-est">{card.estimate}</span>}
      </div>
      <div className="kanban-card-title">{card.title}</div>
      <div className="kanban-card-meta">
        {card.assignee  && <span className="kanban-pill">👤 {card.assignee}</span>}
        {card.iteration && <span className="kanban-pill">🔁 {card.iteration}</span>}
        {card.priority && card.priority !== 'medium' && (
          <span className={`kanban-pill priority-${card.priority}`}>{card.priority}</span>
        )}
      </div>
    </div>
  );
}

export function KanbanPanel() {
  const { state, dispatch, toast } = useApp();
  const [board, setBoard]             = useState(null);
  const [loading, setLoading]         = useState(false);
  const [groupBy, setGroupBy]         = useState('assignee');
  const [typeFilter, setTypeFilter]   = useState('');
  const [iterFilter, setIterFilter]   = useState('');
  const [personFilter, setPersonFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (typeFilter)   params.req_type  = typeFilter;
      if (iterFilter)   params.iteration = iterFilter;
      if (personFilter) params.assignee  = personFilter;
      setBoard(await api.kanban.get(params));
    } catch { setBoard(null); }
    finally { setLoading(false); }
  }, [typeFilter, iterFilter, personFilter]);

  useEffect(() => { load(); }, [load]);

  const allCards = board ? Object.values(board.columns || {}).flat() : [];

  // Build swimlane groups
  const getGroups = () => {
    if (!board || groupBy === 'none') return null; // null = no swimlanes
    const groups = {};
    for (const card of allCards) {
      const key = groupBy === 'assignee'
        ? (card.assignee || '(unassigned)')
        : (card.owner    || '(no owner)');
      if (!groups[key]) groups[key] = new Set();
      groups[key].add(card.uid);
    }
    return groups; // group label -> Set of uids in that group
  };

  const groups   = getGroups();
  const states   = board?.states || [];
  const colCards = (stateId) => board?.columns?.[stateId] || [];

  const createItem = async () => {
    try {
      const item = await api.requirements.create({ title: 'New story', req_type: typeFilter || 'story' });
      dispatch({ type: 'SELECT', uid: item.uid, artefactType: 'requirement' });
      await load(); toast(`Created ${item.id}`, 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  return (
    <div className="kanban-page">
      {/* Toolbar */}
      <div className="kanban-toolbar">
        <div className="kanban-toolbar-section">
          {KANBAN_GROUPINGS.map(g => (
            <button key={g.id}
              className={`kanban-group-btn ${groupBy === g.id ? 'kanban-group-btn--active' : ''}`}
              onClick={() => setGroupBy(g.id)}>
              {g.label}
            </button>
          ))}
        </div>
        <div className="kanban-toolbar-section">
          <select className="kanban-select" value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}>
            <option value="">All types</option>
            {AGILE_TYPES.map(t => (
              <option key={t} value={t}>{TYPE_META[t]?.label || t}</option>
            ))}
          </select>
          <input className="kanban-filter-input" placeholder="Iteration…"
            value={iterFilter} onChange={e => setIterFilter(e.target.value)} />
          <input className="kanban-filter-input" placeholder="Person…"
            value={personFilter} onChange={e => setPersonFilter(e.target.value)} />
          <button className="btn btn-ghost kanban-new-btn" onClick={createItem} title="New item">+</button>
        </div>
      </div>

      {loading && <div className="sidebar-loading"><div className="spinner" /></div>}
      {!loading && !board && <div className="sidebar-empty">Could not load board.</div>}

      {!loading && board && (
        <div className="kanban-body">
          <div className="kanban-columns">
            {states.map(stateId => (
              <div key={stateId} className="kanban-col">
                <div className="kanban-col-header">
                  <span className="kanban-col-label">{stateId.replace(/_/g, '\u00A0')}</span>
                  <span className="kanban-col-count">{colCards(stateId).length}</span>
                </div>
                <div className="kanban-col-body">
                  {/* No swimlanes: render all cards for this state */}
                  {!groups && colCards(stateId).map(card => (
                    <KanbanCard key={card.uid} card={card}
                      isSelected={state.selectedUid === card.uid}
                      onClick={() => dispatch({ type: 'SELECT', uid: card.uid, artefactType: 'requirement' })} />
                  ))}

                  {/* Swimlanes: render one section per group */}
                  {groups && Object.entries(groups).map(([groupLabel, uidSet]) => {
                    const groupColCards = colCards(stateId).filter(c => uidSet.has(c.uid));
                    return (
                      <div key={groupLabel} className="kanban-swimlane">
                        <div className="kanban-swimlane-label">{groupLabel}</div>
                        {groupColCards.length === 0
                          ? <div className="kanban-swimlane-empty" />
                          : groupColCards.map(card => (
                              <KanbanCard key={card.uid} card={card}
                                isSelected={state.selectedUid === card.uid}
                                onClick={() => dispatch({ type: 'SELECT', uid: card.uid, artefactType: 'requirement' })} />
                            ))
                        }
                      </div>
                    );
                  })}

                  {colCards(stateId).length === 0 && !groups && (
                    <div className="kanban-col-empty" />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

