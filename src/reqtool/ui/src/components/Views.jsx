/**
 * Views.jsx -- Read-only pictures of the work: hierarchy, type structure, coverage, impact, flow, burn-up,
 * decision ageing and the principle heatmap. Every picture has a table or text form beside it, and each
 * item opens in the editor when clicked.
 */

import { useMemo, useRef, useState } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import { Panel } from './Advanced/Panel';
import { MermaidView } from './MermaidView';
import { Bar, Status, Tabs, useLoad } from './Insight';
import './Views.css';

const TABS = [
  ['hierarchy', 'Hierarchy'], ['structure', 'Type structure'], ['coverage', 'Coverage'], ['impact', 'Impact'],
  ['flow', 'Flow'], ['burnup', 'Burn-up'], ['decisions', 'Decision ageing'], ['principles', 'Principles'],
];

const Empty = ({ children }) => <div className="ins-muted" data-testid="view-empty">{children}</div>;

/** Download text the browser already holds (the Mermaid source or a table) as a file. */
function saveText(name, text, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

/** Save the drawn diagram (an SVG inside ``host``) as SVG or PNG. */
function saveDiagram(host, name, format) {
  const svg = host?.querySelector('svg');
  if (!svg) return;
  const text = new XMLSerializer().serializeToString(svg);
  if (format === 'svg') { saveText(`${name}.svg`, text, 'image/svg+xml'); return; }
  const img = new Image();
  const box = svg.getBoundingClientRect();
  img.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, box.width * 2); canvas.height = Math.max(1, box.height * 2);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(b => { if (b) { const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = `${name}.png`; a.click(); } });
  };
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
}

function Swatch({ colour }) { return <span className="vw-swatch" style={{ background: colour }} aria-hidden="true" />; }

// --- Hierarchy tree ---------------------------------------------------------------------------------
function HierarchyView({ open, product }) {
  const [types, setTypes] = useState('');
  const [statuses, setStatuses] = useState('');
  const [collapsed, setCollapsed] = useState(() => new Set());
  const data = useLoad(() => api.views.hierarchy({ ...(product ? { product } : {}), ...(types ? { types } : {}), ...(statuses ? { statuses } : {}) }),
    [product, types, statuses]);
  const rows = useMemo(() => {
    const out = []; let hideBelow = null;
    for (const n of data.data?.nodes || []) {
      if (hideBelow !== null && n.depth > hideBelow) continue;
      hideBelow = null; out.push(n);
      if (collapsed.has(n.uid)) hideBelow = n.depth;
    }
    return out;
  }, [data.data, collapsed]);
  const toggle = (uid) => setCollapsed(s => { const x = new Set(s); x.has(uid) ? x.delete(uid) : x.add(uid); return x; });
  return (
    <div>
      <div className="vw-filters">
        <label>Types <input aria-label="Filter by types" placeholder="story,feature" value={types} onChange={e => setTypes(e.target.value.replace(/\s/g, ''))} /></label>
        <label>Statuses <input aria-label="Filter by statuses" placeholder="draft,approved" value={statuses} onChange={e => setStatuses(e.target.value.replace(/\s/g, ''))} /></label>
        <button className="btn btn-ghost" onClick={() => setCollapsed(new Set((data.data?.nodes || []).filter(n => n.children).map(n => n.uid)))}>Collapse all</button>
        <button className="btn btn-ghost" onClick={() => setCollapsed(new Set())}>Expand all</button>
      </div>
      <Status {...data} />
      {data.data && !rows.length && <Empty>No items match.</Empty>}
      <ul className="vw-tree" role="tree">
        {rows.map(n => (
          <li key={n.uid} role="treeitem" aria-level={n.depth + 1} aria-expanded={n.children ? !collapsed.has(n.uid) : undefined}
            className={n.match ? '' : 'vw-dim'} style={{ paddingLeft: n.depth * 18 }}>
            {n.children
              ? <button className="vw-twist" aria-label={`${collapsed.has(n.uid) ? 'Expand' : 'Collapse'} ${n.id}`} onClick={() => toggle(n.uid)}>{collapsed.has(n.uid) ? '▸' : '▾'}</button>
              : <span className="vw-twist" />}
            <Swatch colour={n.colour} />
            <button className="vw-link" onClick={() => open(n.uid)}><span className="mono">{n.id}</span> {n.title}</button>
            <span className="ins-pill">{n.type}</span><span className="ins-pill">{n.status_label}</span>
          </li>
        ))}
      </ul>
      {data.data?.capped && <div className="ins-muted" role="status">Showing {data.data.shown} of {data.data.total} items. Narrow the filters or open a branch to see the rest.</div>}
    </div>
  );
}

// --- Type structure ---------------------------------------------------------------------------------
function StructureView() {
  const data = useLoad(() => api.views.typeStructure(), []);
  const host = useRef(null);
  return (
    <div ref={host}>
      <Status {...data} />
      {data.data && <>
        <div className="vw-filters">
          <button className="btn btn-ghost" onClick={() => saveText('type-structure.mmd', data.data.mermaid)}>Export Mermaid</button>
          <button className="btn btn-ghost" onClick={() => saveDiagram(host.current, 'type-structure', 'svg')}>Save SVG</button>
          <button className="btn btn-ghost" onClick={() => saveDiagram(host.current, 'type-structure', 'png')}>Save PNG</button>
        </div>
        <MermaidView source={data.data.mermaid} title="Which type may sit under which" />
      </>}
    </div>
  );
}

// --- Coverage treemap -------------------------------------------------------------------------------
function Cell({ node, colours, open, depth }) {
  const dominant = Object.entries(node.by).sort((a, b) => b[1] - a[1])[0]?.[0];
  return (
    <div className="vw-cell" style={{ flexGrow: Math.max(1, node.count), borderColor: colours[dominant] || 'var(--border)' }}
      data-testid="coverage-cell">
      <button className="vw-link" onClick={() => open(node.uid)} title={`${node.id}: ${node.count} item(s)`}>
        <span className="mono">{node.id}</span> <span className="vw-count">{node.count}</span>
      </button>
      <div className="vw-stack" aria-hidden="true">
        {Object.entries(node.by).map(([k, v]) => <span key={k} style={{ flexGrow: v, background: colours[k] || '#768390' }} />)}
      </div>
      {node.children.length > 0 && depth < 2 && (
        <div className="vw-cells">{node.children.map(c => <Cell key={c.uid} node={c} colours={colours} open={open} depth={depth + 1} />)}</div>
      )}
    </div>
  );
}

function CoverageView({ open, product }) {
  const [by, setBy] = useState('status');
  const [asTable, setAsTable] = useState(false);
  const data = useLoad(() => api.views.coverage(by, product), [by, product]);
  const d = data.data;
  const flat = useMemo(() => {
    const out = []; const walk = (n, depth) => { out.push({ ...n, depth }); n.children.forEach(c => walk(c, depth + 1)); };
    (d?.roots || []).forEach(r => walk(r, 0)); return out;
  }, [d]);
  const keys = Object.keys(d?.totals || {});
  return (
    <div>
      <div className="vw-filters">
        <label>Colour by <select value={by} onChange={e => setBy(e.target.value)}>
          <option value="status">Status</option><option value="verification">Verification</option></select></label>
        <button className="btn btn-ghost" onClick={() => setAsTable(t => !t)} aria-pressed={asTable}>{asTable ? 'Show treemap' : 'Show table'}</button>
      </div>
      <Status {...data} />
      {d && <ul className="vw-legend" aria-label="Legend">{keys.map(k => <li key={k}><Swatch colour={d.colours[k] || '#768390'} /> {k.replace(/_/g, ' ')} <b>{d.totals[k]}</b></li>)}</ul>}
      {d && !d.roots.length && <Empty>No items yet.</Empty>}
      {d && !asTable && <div className="vw-cells vw-top">{d.roots.map(r => <Cell key={r.uid} node={r} colours={d.colours} open={open} depth={0} />)}</div>}
      {d && asTable && (
        <table className="vw-table" data-testid="coverage-table"><thead><tr><th>Item</th><th>Items below</th>{keys.map(k => <th key={k}>{k.replace(/_/g, ' ')}</th>)}</tr></thead>
          <tbody>{flat.map(n => (
            <tr key={n.uid}><td style={{ paddingLeft: n.depth * 14 }}><button className="vw-link" onClick={() => open(n.uid)}><span className="mono">{n.id}</span> {n.title}</button></td>
              <td>{n.count}</td>{keys.map(k => <td key={k}>{n.by[k] || ''}</td>)}</tr>))}</tbody></table>
      )}
    </div>
  );
}

// --- Impact graph -----------------------------------------------------------------------------------
function ImpactView({ open, focus }) {
  const [uid, setUid] = useState(focus || '');
  const [depth, setDepth] = useState(2);
  const [types, setTypes] = useState('');
  const [asked, setAsked] = useState(focus || '');
  const data = useLoad(() => (asked ? api.views.impact(asked, depth, types) : Promise.resolve(null)), [asked, depth, types]);
  const host = useRef(null);
  const g = data.data;
  return (
    <div ref={host}>
      <form className="vw-filters" onSubmit={e => { e.preventDefault(); setAsked(uid.trim()); }}>
        <label>Item <input aria-label="Item id" placeholder="FR-001" value={uid} onChange={e => setUid(e.target.value)} /></label>
        <label>Depth <select value={depth} onChange={e => setDepth(Number(e.target.value))}>{[1, 2, 3].map(n => <option key={n}>{n}</option>)}</select></label>
        <label>Types <input aria-label="Impact types" placeholder="story,test" value={types} onChange={e => setTypes(e.target.value.replace(/\s/g, ''))} /></label>
        <button className="btn btn-primary" type="submit">Show</button>
      </form>
      {!asked && <Empty>Enter an item id to see what it touches.</Empty>}
      <Status {...data} />
      {g && <>
        <div className="ins-muted" role="status">Showing {g.shown} of {g.total} connected items{g.capped ? ' (nearest first)' : ''}.</div>
        <div className="vw-filters">
          <button className="btn btn-ghost" onClick={() => saveText('impact.mmd', g.mermaid)}>Export Mermaid</button>
          <button className="btn btn-ghost" onClick={() => saveDiagram(host.current, 'impact', 'svg')}>Save SVG</button>
        </div>
        <MermaidView source={g.mermaid} title="Impact graph" />
        <table className="vw-table"><thead><tr><th>Hops</th><th>Item</th><th>Type</th><th>Status</th></tr></thead><tbody>
          {g.nodes.map(n => (<tr key={n.key}><td>{n.distance}</td>
            <td>{n.kind === 'item' ? <button className="vw-link" onClick={() => open(n.key)}><span className="mono">{n.id}</span> {n.title}</button> : <span><span className="mono">{n.id}</span> {n.title}</span>}</td>
            <td>{n.type}</td><td>{n.status || ''}</td></tr>))}</tbody></table>
      </>}
    </div>
  );
}

// --- Flow -------------------------------------------------------------------------------------------
function FlowView({ open }) {
  const [days, setDays] = useState('');
  const data = useLoad(() => api.views.flow(days ? Number(days) : undefined), [days]);
  const [asTable, setAsTable] = useState(false);
  return (
    <div>
      <div className="vw-filters">
        <label>Stuck after (days) <input type="number" min="1" aria-label="Stuck after days" value={days} placeholder={String(data.data?.stuck_days ?? 14)} onChange={e => setDays(e.target.value)} /></label>
        <button className="btn btn-ghost" onClick={() => setAsTable(t => !t)} aria-pressed={asTable}>{asTable ? 'Show funnel' : 'Show table'}</button>
      </div>
      <Status {...data} />
      {data.data?.workflows.map(w => {
        const peak = Math.max(1, ...w.states.map(s => s.count));
        return (
          <section key={w.workflow} className="vw-flow" data-testid={`flow-${w.workflow}`}>
            <h4>{w.workflow} <span className="ins-muted">{w.types.join(', ')} · {w.total} item(s)</span></h4>
            {asTable ? (
              <table className="vw-table"><thead><tr><th>State</th><th>Items</th><th>Average days</th><th>Longest</th><th>Stuck</th></tr></thead>
                <tbody>{w.states.map(s => <tr key={s.state}><td>{s.label}</td><td>{s.count}</td><td>{s.avg_days}</td><td>{s.max_days}</td><td>{s.stuck_count}</td></tr>)}</tbody></table>
            ) : w.states.map(s => (
              <div key={s.state} className="vw-funnel-row">
                <span className="vw-funnel-label">{s.label}</span>
                <span className="vw-funnel-bar" style={{ width: `${(s.count / peak) * 100}%`, background: s.colour }} />
                <span className="vw-funnel-n">{s.count}</span>
                {s.stuck_count > 0 && <span className="ins-pill red" title={`Longer than ${s.threshold} days in this state`}>{s.stuck_count} stuck</span>}
                {s.stuck.slice(0, 3).map(i => <button key={i.uid} className="vw-link" onClick={() => open(i.uid)}><span className="mono">{i.id}</span> {i.days}d</button>)}
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}

// --- Burn-up ----------------------------------------------------------------------------------------
function BurnupChart({ series }) {
  const W = 560, H = 200, P = 28;
  const max = Math.max(1, ...series.map(p => p.scope));
  const x = (i) => P + (series.length < 2 ? 0 : (i / (series.length - 1)) * (W - 2 * P));
  const y = (v) => H - P - (v / max) * (H - 2 * P);
  const line = (key) => series.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p[key])}`).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="vw-chart" role="img" aria-label="Burn-up chart: scope and done over time">
      <line x1={P} y1={H - P} x2={W - P} y2={H - P} stroke="var(--border)" /><line x1={P} y1={P} x2={P} y2={H - P} stroke="var(--border)" />
      <text x={4} y={P} fontSize="10" fill="currentColor">{max}</text><text x={P} y={H - 8} fontSize="10" fill="currentColor">{series[0]?.date}</text>
      <text x={W - P} y={H - 8} fontSize="10" textAnchor="end" fill="currentColor">{series[series.length - 1]?.date}</text>
      <path d={line('scope')} fill="none" stroke="#d29922" strokeWidth="2" /><path d={line('done')} fill="none" stroke="#3fb950" strokeWidth="2" />
    </svg>
  );
}

function BurnupView() {
  const its = useLoad(() => api.iterations.list(), []);
  const [id, setId] = useState('');
  const list = Array.isArray(its.data) ? its.data : its.data?.iterations || [];
  const chosen = id || list[0]?.id || '';
  const data = useLoad(() => (chosen ? api.views.burnup(chosen) : Promise.resolve(null)), [chosen]);
  return (
    <div>
      <Status loading={its.loading} error={its.error} />
      {!its.loading && !list.length && <Empty>No iterations yet. Create one under Iterations &amp; Gates.</Empty>}
      {list.length > 0 && <div className="vw-filters"><label>Iteration <select value={chosen} onChange={e => setId(e.target.value)}>
        {list.map(i => <option key={i.id} value={i.id}>{i.title || i.id}</option>)}</select></label></div>}
      <Status loading={data.loading && !!chosen} error={data.error} />
      {data.data && <>
        <div className="ins-muted">{data.data.done} of {data.data.scope} {data.data.unit} done · {data.data.items} item(s)</div>
        {data.data.series.length ? <BurnupChart series={data.data.series} /> : <Empty>No items in this iteration yet.</Empty>}
        <ul className="vw-legend"><li><span className="vw-swatch" style={{ background: '#d29922' }} /> Scope</li><li><span className="vw-swatch" style={{ background: '#3fb950' }} /> Done</li></ul>
        <div className="ins-muted">{data.data.note}</div>
        {data.data.series.length > 0 && <table className="vw-table"><thead><tr><th>Date</th><th>Scope</th><th>Done</th></tr></thead>
          <tbody>{data.data.series.map(p => <tr key={p.date}><td>{p.date}</td><td>{p.scope}</td><td>{p.done}</td></tr>)}</tbody></table>}
      </>}
    </div>
  );
}

// --- Decision ageing --------------------------------------------------------------------------------
function DecisionsView({ open, openDecision }) {
  const data = useLoad(() => api.views.decisions(), []);
  const d = data.data;
  return (
    <div>
      <Status {...data} />
      {d && !d.decisions.length && <Empty>No open decisions or questions.</Empty>}
      {d?.decisions.map(x => (
        <div key={x.uid} className="vw-decision">
          <div className="ins-row"><span className="ins-pill">{x.kind}</span><button className="vw-link grow" onClick={() => openDecision?.(x.uid)}><span className="mono">{x.id}</span> {x.title}</button>
            <span className={`ins-pill ${x.age_days > 30 ? 'red' : x.age_days > 14 ? 'amber' : ''}`}>{x.age_days}d open</span>
            <span className="ins-pill">blocks {x.blocks.length}</span></div>
          <div className="vw-blocks">{x.blocks.map(b => b.uid
            ? <button key={b.id} className="vw-link" onClick={() => open(b.uid)}><span className="mono">{b.id}</span></button> : <span key={b.id} className="mono">{b.id}</span>)}</div>
        </div>
      ))}
    </div>
  );
}

// --- Principle heatmap ------------------------------------------------------------------------------
function PrinciplesView({ open }) {
  const data = useLoad(() => api.views.principles(), []);
  const [picked, setPicked] = useState(null);
  const cites = useLoad(() => (picked ? Promise.all(picked.ids.map(id => api.views.citations(id).catch(() => []))).then(a => a.flat()) : Promise.resolve([])), [picked]);
  const d = data.data;
  const shade = (n) => (d?.max ? `rgba(63,185,80,${0.12 + 0.7 * (n / d.max)})` : 'transparent');
  return (
    <div>
      <Status {...data} />
      {d && !d.areas.length && <Empty>No principles yet.</Empty>}
      {d && <div className="ins-muted" role="status">{d.uncited} of {d.principles} principles are cited by nothing · {d.ungoverned} of {d.requirements} requirements cite no principle.</div>}
      {d?.areas.map(a => (
        <section key={a.area}><h4>{a.label}</h4>
          <div className="vw-heat">{a.cells.filter(c => c.principles).map(c => (
            <button key={c.category} className={`vw-heat-cell ${c.cited === 0 ? 'vw-heat-none' : ''}`} style={{ background: c.cited ? shade(c.citations) : undefined }}
              onClick={() => setPicked({ ...c, area: a.label, ids: c.uids || [] })} aria-label={`${a.label} ${c.label}: ${c.citations} citation(s), ${c.cited} of ${c.principles} principles cited`}>
              <b>{c.label}</b><span>{c.cited}/{c.principles} cited</span><span>{c.citations} link(s)</span>
            </button>))}</div></section>
      ))}
      {picked && <div className="vw-picked"><h4>{picked.area} / {picked.label}</h4>
        <div className="ins-muted">Principles: {picked.ids.join(', ')}</div>
        {cites.data?.length ? cites.data.map(r => <button key={r.uid} className="vw-link" onClick={() => open(r.uid)}><span className="mono">{r.id}</span> {r.title}</button>)
          : <Empty>{picked.uncited.length ? `Not cited by anything: ${picked.uncited.join(', ')}` : 'No requirement cites these yet.'}</Empty>}
      </div>}
      {d?.ungoverned_sample.length > 0 && <details><summary>Requirements that cite no principle ({d.ungoverned})</summary>
        {d.ungoverned_sample.map(r => <div key={r.uid}><button className="vw-link" onClick={() => open(r.uid)}><span className="mono">{r.id}</span> {r.title}</button></div>)}</details>}
    </div>
  );
}

export function ViewsPanel({ onClose, initial = 'hierarchy' }) {
  const { state, dispatch } = useApp();
  const [tab, setTab] = useState(initial);
  const product = state.activeProduct?.id;
  const open = (uid) => { dispatch({ type: 'SELECT', uid, artefactType: 'requirement' }); onClose(); };
  const openDecision = (uid) => { dispatch({ type: 'SELECT', uid, artefactType: 'decision' }); onClose(); };
  return (
    <Panel title="Views" onClose={onClose} width={860}>
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {tab === 'hierarchy' && <HierarchyView open={open} product={product} />}
      {tab === 'structure' && <StructureView />}
      {tab === 'coverage' && <CoverageView open={open} product={product} />}
      {tab === 'impact' && <ImpactView open={open} focus={state.selectedUid && state.selectedType !== 'decision' ? state.selectedUid : ''} />}
      {tab === 'flow' && <FlowView open={open} />}
      {tab === 'burnup' && <BurnupView />}
      {tab === 'decisions' && <DecisionsView open={open} openDecision={openDecision} />}
      {tab === 'principles' && <PrinciplesView open={open} />}
    </Panel>
  );
}

// --- Roadmap board ----------------------------------------------------------------------------------
const UNPLANNED = 'unplanned';

/** Themes as lanes, releases (or iterations) as columns. Editors drag a card, or use its menu, to re-plan it. */
export function RoadmapBoard({ open, canEdit }) {
  const [groupBy, setGroupBy] = useState('release');
  const data = useLoad(() => api.views.roadmapBoard(groupBy), [groupBy]);
  const [over, setOver] = useState('');
  const [error, setError] = useState('');
  const b = data.data;
  const move = async (card, column) => {
    if (column === card.column) return;
    setError('');
    try {
      await api.requirements.update(card.uid, groupBy === 'release'
        ? { target_release: column === UNPLANNED ? null : column } : { iteration: column === UNPLANNED ? null : column });
      data.reload();
    } catch (e) { setError(e.message); }
  };
  const critical = new Set(b?.critical_chain || []);
  const cols = b?.columns || [];
  return (
    <div className="rb" data-testid="roadmap-board">
      <div className="vw-filters">
        <label>Columns <select value={groupBy} onChange={e => setGroupBy(e.target.value)}>
          <option value="release">Release</option><option value="iteration">Iteration</option></select></label>
        {!canEdit && <span className="ins-muted">Read-only: your role cannot re-plan items.</span>}
      </div>
      <Status {...data} />
      {error && <div className="ins-error" role="alert">{error}</div>}
      {b && !b.lanes.length && <Empty>No themes or initiatives yet.</Empty>}
      {b && b.lanes.length > 0 && (
        <div className="rb-grid" style={{ gridTemplateColumns: `140px repeat(${cols.length}, minmax(150px, 1fr))` }}>
          <div />{cols.map(c => <div key={c} className="rb-head">{c}</div>)}
          {b.lanes.map(l => (
            <div key={l.uid} style={{ display: 'contents' }}>
              <div className="rb-lane"><button className="vw-link" onClick={() => open(l.uid)}><span className="mono">{l.id}</span> {l.title}</button></div>
              {cols.map(c => (
                <div key={c} className={`rb-col ${over === `${l.uid}|${c}` ? 'rb-over' : ''}`} data-testid={`rb-${l.id}-${c}`}
                  onDragOver={e => { if (canEdit) { e.preventDefault(); setOver(`${l.uid}|${c}`); } }}
                  onDragLeave={() => setOver('')}
                  onDrop={e => { e.preventDefault(); setOver(''); const uid = e.dataTransfer.getData('text/plain'); const card = b.cards.find(x => x.uid === uid); if (card && canEdit) move(card, c); }}>
                  {b.cards.filter(x => x.lane === l.uid && x.column === c).map(card => (
                    <div key={card.uid} className={`rb-card ${critical.has(card.id) ? 'rb-crit' : ''}`} draggable={canEdit}
                      onDragStart={e => e.dataTransfer.setData('text/plain', card.uid)} data-testid={`rb-card-${card.id}`}>
                      <button className="vw-link" onClick={() => open(card.uid)}><span className="mono">{card.id}</span> {card.title}</button>
                      <Bar value={card.progress_pct} label={`${card.id} progress`} />
                      {canEdit && <select aria-label={`Move ${card.id} to`} value={card.column} onChange={e => move(card, e.target.value)}>
                        {cols.map(x => <option key={x} value={x}>{x}</option>)}</select>}
                    </div>))}
                </div>))}
            </div>))}
        </div>
      )}
      {b?.dependencies.length > 0 && <div className="vw-picked"><h4>Dependencies</h4>
        {b.critical_chain.length > 1 && <div>Longest chain: <b>{b.critical_chain.join(' → ')}</b></div>}
        {b.dependencies.map(d => <div key={`${d.from}${d.to}`} className={d.critical ? 'rb-crit' : ''}><span className="mono">{d.from_id}</span> depends on <span className="mono">{d.to_id}</span></div>)}</div>}
      {b?.needs.length > 0 && <details><summary>Stakeholder needs ({b.needs.length})</summary>
        {b.needs.map(n => <div key={n.uid}><button className="vw-link" onClick={() => open(n.uid)}><span className="mono">{n.id}</span> {n.title}</button> {n.links.length ? `→ ${n.links.join(', ')}` : '(not linked to a theme or initiative)'}</div>)}</details>}
    </div>
  );
}

// --- Traceability grid ------------------------------------------------------------------------------
const PAGE = 50;

export function TraceGrid({ product }) {
  const { dispatch } = useApp();
  const [columns, setColumns] = useState('tests');
  const [gaps, setGaps] = useState(false);
  const [page, setPage] = useState(0);
  const params = { columns, gaps, offset: page * PAGE, limit: PAGE, ...(product ? { product } : {}) };
  const data = useLoad(() => api.traceability.grid(params), [columns, gaps, page, product]);
  const g = data.data;
  const pages = g ? Math.max(1, Math.ceil(g.total / PAGE)) : 1;
  return (
    <div data-testid="trace-grid">
      <div className="vw-filters">
        <label>Across the top <select value={columns} onChange={e => { setColumns(e.target.value); setPage(0); }}>
          <option value="tests">Tests</option><option value="modules">Modules</option><option value="decisions">Decisions</option></select></label>
        <label><input type="checkbox" checked={gaps} onChange={e => { setGaps(e.target.checked); setPage(0); }} /> Only requirements with no link</label>
        <a className="btn btn-ghost" href={api.traceability.gridCsvUrl({ columns, gaps, ...(product ? { product } : {}) })} download>Download CSV</a>
      </div>
      <Status {...data} />
      {g && <div className="ins-muted" role="status">{g.total} requirement(s){gaps ? ' without a link' : ''} · {g.without_links} of {g.all_requirements} have no {columns.replace(/s$/, '')} link{g.columns_total > g.columns.length ? ` · showing ${g.columns.length} of ${g.columns_total} columns` : ''}</div>}
      {g && !g.rows.length && <Empty>{gaps ? 'Every requirement has a link.' : 'No requirements.'}</Empty>}
      {g?.rows.length > 0 && (
        <div style={{ overflowX: 'auto' }}><table className="vw-table"><thead><tr><th>Requirement</th>{g.columns.map(c => <th key={c.key} title={`${c.count} requirement(s)`}>{c.key}</th>)}</tr></thead>
          <tbody>{g.rows.map(r => (
            <tr key={r.uid}><td><button className="vw-link" onClick={() => dispatch({ type: 'SELECT', uid: r.uid, artefactType: 'requirement' })}><span className="mono">{r.id}</span> {r.title}</button>{!r.linked && <span className="ins-pill red"> no link</span>}</td>
              {g.columns.map(c => <td key={c.key} title={r.cells[c.key]?.state || ''}>{r.cells[c.key] ? '✓' : ''}</td>)}</tr>))}</tbody></table></div>
      )}
      {pages > 1 && <div className="vw-filters"><button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page + 1} of {pages}</span><button className="btn btn-ghost" disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>Next</button></div>}
    </div>
  );
}
