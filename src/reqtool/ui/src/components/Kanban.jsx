/**
 * Kanban.jsx -- Full-width kanban board.
 * - Columns = workflow states
 * - Swimlanes = by person / team / all
 * - Drag and drop between columns (calls POST /requirements/{uid}/transition)
 * - Click a card to open it in the editor (rendered in App.jsx alongside the board)
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

const GROUPINGS = [
  { id: 'assignee', label: 'By Person' },
  { id: 'owner',    label: 'By Team'   },
  { id: 'none',     label: 'All'       },
];

// ---------------------------------------------------------------------------
// KanbanCard -- draggable, selectable
// ---------------------------------------------------------------------------
function KanbanCard({ card, isSelected, onClick, onDragStart }) {
  const meta = TYPE_META[card.req_type] || {};
  return (
    <div
      className={`kanban-card ${isSelected ? 'kanban-card--selected' : ''}`}
      style={{ borderLeft: `3px solid ${meta.colour || 'var(--border)'}` }}
      draggable
      onDragStart={e => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', card.uid);
        onDragStart?.(card.uid);
      }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onClick?.()}
      title={`${card.id}: ${card.title}\nDrag to move between states`}
    >
      <div className="kanban-card-header">
        <span className="kanban-card-id mono">{card.id}</span>
        <span className="kanban-card-type">{meta.icon || ''}</span>
        {card.estimate != null && <span className="kanban-card-est">{card.estimate}pt</span>}
      </div>
      <div className="kanban-card-title">{card.title}</div>
      {(card.assignee || card.iteration || (card.priority && card.priority !== 'medium')) && (
        <div className="kanban-card-meta">
          {card.assignee  && <span className="kanban-pill">👤 {card.assignee}</span>}
          {card.iteration && <span className="kanban-pill">🔁 {card.iteration}</span>}
          {card.priority && card.priority !== 'medium' && (
            <span className={`kanban-pill priority-${card.priority}`}>{card.priority}</span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// KanbanColumn -- drop target
// ---------------------------------------------------------------------------
function KanbanColumn({ stateId, cards, groups, isSelected, onCardClick, onDrop, draggingUid }) {
  const [dragOver, setDragOver] = useState(false);
  const label = stateId.replace(/_/g, ' ');

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOver(true);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const uid = e.dataTransfer.getData('text/plain');
    if (uid) onDrop(uid, stateId);
  };

  return (
    <div
      className={`kanban-col ${dragOver ? 'kanban-col--drag-over' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <div className="kanban-col-header">
        <span className="kanban-col-label">{label}</span>
        <span className="kanban-col-count">{cards.length}</span>
      </div>
      <div className="kanban-col-body">
        {dragOver && cards.length === 0 && (
          <div className="kanban-drop-hint">Drop here</div>
        )}
        {!groups && cards.map(card => (
          <KanbanCard key={card.uid} card={card}
            isSelected={isSelected(card.uid)}
            onClick={() => onCardClick(card)}
            onDragStart={() => {}} />
        ))}
        {groups && Object.entries(groups).map(([groupLabel, uidSet]) => {
          const groupCards = cards.filter(c => uidSet.has(c.uid));
          return (
            <div key={groupLabel} className="kanban-swimlane">
              <div className="kanban-swimlane-label">{groupLabel}</div>
              {groupCards.length === 0
                ? <div className="kanban-swimlane-empty" />
                : groupCards.map(card => (
                    <KanbanCard key={card.uid} card={card}
                      isSelected={isSelected(card.uid)}
                      onClick={() => onCardClick(card)}
                      onDragStart={() => {}} />
                  ))
              }
            </div>
          );
        })}
        {cards.length === 0 && !dragOver && (
          <div className="kanban-col-empty">Drop a card here to move it to <em>{label}</em></div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KanbanPanel -- exported, rendered in App's <main>
// ---------------------------------------------------------------------------
export function KanbanPanel() {
  const { state, dispatch, toast } = useApp();
  const [board, setBoard]               = useState(null);
  const [loading, setLoading]           = useState(false);
  const [groupBy, setGroupBy]           = useState('none');
  const [typeFilter, setTypeFilter]     = useState('');
  const [iterFilter, setIterFilter]     = useState('');
  const [personFilter, setPersonFilter] = useState('');
  const [draggingUid, setDraggingUid]   = useState(null);
  const [moving, setMoving]             = useState(null); // uid being transitioned

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (typeFilter)   params.req_type  = typeFilter;
      if (iterFilter)   params.iteration = iterFilter;
      if (personFilter) params.assignee  = personFilter;
      setBoard(await api.kanban.get(params));
    } catch {
      setBoard(null);
    } finally {
      setLoading(false);
    }
  }, [typeFilter, iterFilter, personFilter]);

  useEffect(() => { load(); }, [load]);

  // Reload when a save happens (selectedUid changes away = item was saved)
  useEffect(() => {
    if (!state.selectedUid) load();
  }, [state._lastCommit]);

  const allCards = board ? Object.values(board.columns || {}).flat() : [];

  const getGroups = () => {
    if (!board || groupBy === 'none') return null;
    const groups = {};
    for (const card of allCards) {
      const key = groupBy === 'assignee'
        ? (card.assignee || '(unassigned)')
        : (card.owner    || '(no owner)');
      if (!groups[key]) groups[key] = new Set();
      groups[key].add(card.uid);
    }
    return groups;
  };

  const groups   = getGroups();
  const states   = board?.states || [];
  const colCards = (stateId) => board?.columns?.[stateId] || [];

  const handleCardClick = (card) => {
    if (state.selectedUid === card.uid) {
      dispatch({ type: 'DESELECT' });
    } else {
      dispatch({ type: 'SELECT', uid: card.uid, artefactType: 'requirement' });
    }
  };

  const handleDrop = async (uid, targetState) => {
    setDraggingUid(null);
    // Find which state the card is currently in
    const currentState = Object.entries(board?.columns || {})
      .find(([, cards]) => cards.some(c => c.uid === uid))?.[0];
    if (currentState === targetState) return; // no-op

    setMoving(uid);
    // Optimistic update
    setBoard(prev => {
      if (!prev) return prev;
      const cols = { ...prev.columns };
      const card = Object.values(cols).flat().find(c => c.uid === uid);
      if (!card) return prev;
      cols[currentState] = (cols[currentState] || []).filter(c => c.uid !== uid);
      cols[targetState]  = [...(cols[targetState] || []), { ...card, status: targetState }];
      return { ...prev, columns: cols };
    });

    try {
      await api.requirements.transition(uid, targetState);
      toast(`Moved to ${targetState.replace(/_/g, ' ')}`, 'success', 1500);
    } catch (err) {
      toast(`Could not move: ${err.message}`, 'error');
      load(); // revert
    } finally {
      setMoving(null);
    }
  };

  const createItem = async () => {
    try {
      const item = await api.requirements.create({
        title: 'New story',
        req_type: typeFilter || 'story',
      });
      dispatch({ type: 'SELECT', uid: item.uid, artefactType: 'requirement' });
      await load();
      toast(`Created ${item.id}`, 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  return (
    <div className="kanban-page">
      <div className="kanban-toolbar">
        <div className="kanban-toolbar-section">
          {GROUPINGS.map(g => (
            <button key={g.id}
              className={`kanban-group-btn ${groupBy === g.id ? 'kanban-group-btn--active' : ''}`}
              onClick={() => setGroupBy(g.id)}>
              {g.label}
            </button>
          ))}
        </div>
        <div className="kanban-toolbar-section" style={{ flex: 1 }}>
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
        </div>
        <div className="kanban-toolbar-section">
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: '4px 8px' }}
            onClick={load} title="Refresh board">↺ Refresh</button>
          <button className="btn btn-primary" style={{ fontSize: 11, padding: '4px 10px' }}
            onClick={createItem} title="New work item">+ New</button>
        </div>
      </div>

      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1 }}>
          <div className="spinner" />
        </div>
      )}

      {!loading && !board && (
        <div className="kanban-empty">
          <div>Board unavailable</div>
          <div style={{ fontSize: 12, marginTop: 8, color: 'var(--text-muted)' }}>
            The /kanban endpoint is not responding. Check that <code>req serve</code> is running.
          </div>
          <button className="btn btn-secondary" style={{ marginTop: 12 }} onClick={load}>↺ Retry</button>
        </div>
      )}

      {!loading && board && states.length === 0 && (
        <div className="kanban-empty">
          <div>No workflow states configured</div>
          <div style={{ fontSize: 12, marginTop: 8, color: 'var(--text-muted)' }}>
            Run <code>req init defaults</code> to set up the sprint workflow.
          </div>
        </div>
      )}

      {!loading && board && states.length > 0 && (
        <div className="kanban-body"
          onDragEnd={() => setDraggingUid(null)}>
        <div className="kanban-columns">
            {states.map(stateId => (
              <KanbanColumn
                key={stateId}
                stateId={stateId}
                cards={colCards(stateId)}
                groups={groups}
                isSelected={uid => state.selectedUid === uid}
                onCardClick={handleCardClick}
                onDrop={handleDrop}
                draggingUid={draggingUid}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
