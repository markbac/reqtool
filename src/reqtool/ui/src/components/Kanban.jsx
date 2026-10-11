/**
 * Kanban.jsx -- Full-width kanban board.
 * - Columns = workflow states
 * - Swimlanes = by person / team / all
 * - Drag and drop between columns (calls POST /requirements/{uid}/transition)
 * - Click a card to open it in the editor (rendered in App.jsx alongside the board)
 */

import { useState, useEffect, useCallback } from 'react';
import { useApp, useCan } from '../AppContext';
import { api } from '../api';
import { TransitionDialog, getPath, setPath, DIALOG_FIELDS } from './TransitionDialog';
import { needsInput } from './Editor';
import { createAndOpen, typeBody } from '../createItem';
import { ForceDialog, SuggestDialog, ruleBlock, rollupSummary } from './RuleDialogs';
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

// Theme and Initiative are strategic: they live on the roadmap, not on the delivery board (MOD-13).
const AGILE_TYPES = ['epic', 'feature', 'story', 'task', 'bug', 'spike'];
const UNCOLUMNED = '_uncolumned';

const GROUPINGS = [
  { id: 'assignee', label: 'By Person' },
  { id: 'owner',    label: 'By Team'   },
  { id: 'none',     label: 'All'       },
];

// ---------------------------------------------------------------------------
// KanbanCard -- draggable, selectable
// ---------------------------------------------------------------------------
function KanbanCard({ card, isSelected, onClick, onDragStart, canMove, states, current, onMove }) {
  const meta = TYPE_META[card.req_type] || {};
  return (
    <div
      className={`kanban-card ${isSelected ? 'kanban-card--selected' : ''}`}
      style={{ borderLeft: `3px solid ${meta.colour || 'var(--border)'}` }}
      draggable={canMove}
      onDragStart={e => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', card.uid);
        onDragStart?.(card.uid);
      }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onClick?.()}
      title={canMove ? `${card.id}: ${card.title}\nDrag to move between states` : `${card.id}: ${card.title}`}
    >
      <div className="kanban-card-header">
        <span className="kanban-card-id mono">{card.id}</span>
        <span className="kanban-card-type">{meta.icon || ''}</span>
        {card.estimate != null && <span className="kanban-card-est">{card.estimate}pt</span>}
      </div>
      <div className="kanban-card-title">{card.title}</div>
      {(card.parent || card.blocked_by?.length > 0 || card.open_children > 0 || card.rule_problem) && (
        <div className="kanban-card-meta" data-testid="card-detail">
          {card.parent && <span className="kanban-pill" title={`Parent: ${card.parent.title}`}>↑ {card.parent.id}</span>}
          {card.blocked_by?.length > 0 && <span className="kanban-pill priority-high" title="Waiting on items that are not done">⛔ {card.blocked_by.map(b => b.id).join(', ')}</span>}
          {card.open_children > 0 && <span className="kanban-pill" title="Children not yet done">{card.open_children} open</span>}
          {card.rule_problem && <span className="kanban-pill priority-critical" title={card.rule_problem} aria-label={`Breaks a rule: ${card.rule_problem}`}>⚠ rule</span>}
        </div>
      )}
      {canMove && (
        <select className="kanban-move" aria-label={`Move ${card.id} to`} value={current}
          onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}
          onChange={e => onMove(card.uid, e.target.value)}>
          {states.filter(x => x !== UNCOLUMNED).map(x => <option key={x} value={x}>{x.replace(/_/g, ' ')}</option>)}
          {current === UNCOLUMNED && <option value={UNCOLUMNED}>(no matching column)</option>}
        </select>
      )}
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
function KanbanColumn({ stateId, cards, groups, isSelected, onCardClick, onDrop, draggingUid, canMove, states, onMove }) {
  const [dragOver, setDragOver] = useState(false);
  const label = stateId === UNCOLUMNED ? 'no matching column' : stateId.replace(/_/g, ' ');

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOver(true);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const uid = e.dataTransfer.getData('text/plain');
    if (uid && canMove) onDrop(uid, stateId);
  };

  return (
    <div
      className={`kanban-col ${dragOver ? 'kanban-col--drag-over' : ''}`}
      onDragOver={canMove ? handleDragOver : undefined}
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
            canMove={canMove} states={states} current={stateId} onMove={onMove}
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
                      canMove={canMove} states={states} current={stateId} onMove={onMove}
                      onDragStart={() => {}} />
                  ))
              }
            </div>
          );
        })}
        {cards.length === 0 && !dragOver && (
          <div className="kanban-col-empty">{canMove ? <>Drop a card here to move it to <em>{label}</em></> : 'No cards'}</div>
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
  const can = useCan();
  const canMove = can('write');
  const [guarded, setGuarded]           = useState(null); // a move that needs input: { option, req }
  const [board, setBoard]               = useState(null);
  const [loading, setLoading]           = useState(false);
  const [groupBy, setGroupBy]           = useState('none');
  const [typeFilter, setTypeFilter]     = useState('');
  const [iterFilter, setIterFilter]     = useState('');
  const [personFilter, setPersonFilter] = useState('');
  const [draggingUid, setDraggingUid]   = useState(null);
  const [moving, setMoving]             = useState(null); // uid being transitioned
  const [forceBlock, setForceBlock]       = useState(null); // a move a rule blocked, waiting for a reason
  const [suggested, setSuggested]         = useState(null); // roll-up moves a rule proposes

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
  // Cards whose status has no column are shown in a visible lane instead of disappearing.
  const states   = [...(board?.states || []), ...(board?.columns?.[UNCOLUMNED]?.length ? [UNCOLUMNED] : [])];
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
    if (currentState === targetState || targetState === UNCOLUMNED) return; // no-op

    // A move that needs data the item lacks (or has a rule to explain) opens the same pop-up as the editor.
    if (await askFirst(uid, targetState)) return;

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

    await moveCard(uid, targetState, {});
  };

  /** Open the pop-up when the move needs input. Returns true when it did, so the caller stops. */
  const askFirst = async (uid, targetState) => {
    try {
      const [req, listed] = await Promise.all([api.requirements.get(uid), api.requirements.transitions(uid)]);
      const option = (listed.transitions || []).find(t => t.to === targetState);
      if (option && needsInput(option, req)) { setGuarded({ option, req }); return true; }
    } catch { /* the move itself reports the problem */ }
    return false;
  };

  /** From a card's menu: same path as a drop, without the optimistic update. */
  const menuMove = async (uid, targetState) => {
    const from = Object.entries(board?.columns || {}).find(([, cards]) => cards.some(c => c.uid === uid))?.[0];
    if (!targetState || from === targetState || targetState === UNCOLUMNED) return;
    if (await askFirst(uid, targetState)) return;
    setMoving(uid);
    await moveCard(uid, targetState, {});
  };

  /** Apply the pop-up: save the fields it collected, add new criteria, then make the move. */
  const applyGuarded = async (next, save, extras) => {
    const { option, req } = guarded;
    setGuarded(null);
    if (!save) { toast('Open the item to edit a draft', 'info'); return; }
    try {
      const patch = {};
      for (const f of DIALOG_FIELDS) {
        const before = getPath(req, f.path), after = getPath(next, f.path);
        if (JSON.stringify(before ?? '') !== JSON.stringify(after ?? '')) {
          if (f.path.startsWith('content.')) patch.content = { ...(patch.content || req.content || {}), ...setPath({}, f.path, after).content };
          else patch[f.path] = after;
        }
      }
      if (Object.keys(patch).length) await api.requirements.update(req.uid, patch);
      for (const ac of next.acceptance_criteria || []) {
        if (String(ac.uid).startsWith('new-')) await api.requirements.addAc(req.uid, { text: ac.text });
      }
      setMoving(req.uid);
      await moveCard(req.uid, option.to, { force: extras.force || undefined, reason: extras.reason || undefined }, true);
      if (extras.accept?.length) for (const m of extras.accept) await moveCard(m.uid, m.to, {});
    } catch (err) { toast(`Could not move: ${err.message}`, 'error'); }
    load();
  };

  const moveCard = async (uid, targetState, extra, quiet = false) => {
    try {
      const result = await api.requirements.transition(uid, targetState, extra);
      window.dispatchEvent(new Event('reqtool:tree-changed'));
      const said = rollupSummary(result.rules);
      toast(said || `Moved to ${targetState.replace(/_/g, ' ')}`, 'success', said ? 5000 : 1500);
      if (!quiet && result.rules?.suggested?.length) setSuggested(result.rules.suggested);
      if (result.rules || extra.force) load();   // a roll-up may have moved other cards
    } catch (err) {
      const block = ruleBlock(err);
      if (block) setForceBlock({ block, uid, targetState });
      else toast(`Could not move: ${err.message}`, 'error');
      load(); // revert
    } finally {
      setMoving(null);
    }
  };

  const createItem = async () => {
    const type = typeFilter || 'story';
    const label = state.hierarchy?.types?.[type]?.label || TYPE_META[type]?.label || type;
    const item = await createAndOpen(typeBody(type, label), { dispatch, toast, hasProduct: !!state.activeProduct });
    if (item) { await load(); toast(`Created ${item.id}`, 'success'); }
  };

  // Types the board can show: the repository's own, without the strategic layers that live on the roadmap.
  const boardTypes = Object.keys(state.hierarchy?.types || {}).filter(t => !['theme', 'initiative', 'stakeholder_need'].includes(t));
  const typeChoices = boardTypes.length ? boardTypes : AGILE_TYPES;

  return (
    <div className="kanban-page">
      {forceBlock && (
        <ForceDialog block={forceBlock.block} onCancel={() => setForceBlock(null)}
          onForce={(reason) => { const f = forceBlock; setForceBlock(null); moveCard(f.uid, f.targetState, { force: true, reason }); }} />
      )}
      {guarded && (
        <TransitionDialog option={guarded.option} draft={guarded.req} onCancel={() => { setGuarded(null); load(); }} onApply={applyGuarded} />
      )}
      {suggested && (
        <SuggestDialog suggestions={suggested} onDismiss={() => setSuggested(null)}
          onAccept={async (picked) => {
            setSuggested(null);
            for (const m of picked) await moveCard(m.uid, m.to, {});
          }} />
      )}
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
            {typeChoices.map(t => (
              <option key={t} value={t}>{state.hierarchy?.types?.[t]?.label || TYPE_META[t]?.label || t}</option>
            ))}
          </select>
          <select className="kanban-select" aria-label="Iteration" value={iterFilter} onChange={e => setIterFilter(e.target.value)}>
            <option value="">All iterations</option>
            {(board?.iterations || []).map(i => <option key={i} value={i}>{i}</option>)}
          </select>
          <select className="kanban-select" aria-label="Person" value={personFilter} onChange={e => setPersonFilter(e.target.value)}>
            <option value="">Everyone</option>
            {(board?.people || []).map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="kanban-toolbar-section">
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: '4px 8px' }}
            onClick={load} title="Refresh board">↺ Refresh</button>
          {canMove && <button className="btn btn-primary" style={{ fontSize: 11, padding: '4px 10px' }}
            onClick={createItem} title="New work item">+ New</button>}
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

      {!loading && board && (board.states || []).length === 0 && states.length === 0 && (
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
                canMove={canMove} states={states} onMove={menuMove}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
