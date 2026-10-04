/**
 * ItemInsight.jsx -- Per-requirement traceability, lifecycle, progress, quality and reviews
 * (ENH-01/02/05, FEAT-04/06, UI-07), and the editor/git/version status strip (UI-08).
 */

import { useEffect, useState } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import { Bar, pct } from './Insight';
import './Insight.css';

/** Where the item's changes are: in the editor, on disk, staged or committed (UI-08). */
export function StatusStrip({ uid, isDirty, version }) {
  const { state } = useApp();
  const [git, setGit] = useState(null);
  useEffect(() => {
    let live = true;
    api.git.status().then(s => live && setGit(s)).catch(() => live && setGit(null));
    return () => { live = false; };
  }, [uid, isDirty, state._lastCommit]);

  const path = `requirements/${uid}.yaml`;
  const in_ = (list) => (list || []).some(p => p === path || p.endsWith(`/${path}`));
  let gitState = 'unknown';
  if (git) gitState = in_(git.staged) ? 'staged' : (in_(git.unstaged) || in_(git.untracked)) ? 'modified' : 'clean';
  const editor = isDirty ? 'modified' : 'saved';
  const pending = isDirty || gitState === 'modified' || gitState === 'staged';
  return (
    <div className="ins-row" role="status" aria-label="Change status" style={{ gap: 14 }}>
      <span>Editor: <b className={`ins-pill ${isDirty ? 'amber' : 'green'}`}>{editor}</b></span>
      <span>Git: <b className={`ins-pill ${gitState === 'clean' ? 'green' : gitState === 'unknown' ? '' : 'amber'}`}>{gitState}</b></span>
      <span>Version: <b className="mono">v{version}</b>{pending && <span className="ins-muted"> (next version is set when you commit)</span>}</span>
    </div>
  );
}

function Lifecycle({ lc }) {
  const idx = lc.stages.indexOf(lc.stage);
  return (
    <>
      <div className="ins-strip" role="list" aria-label="Lifecycle">
        {lc.stages.map((s, i) => (
          <div key={s} role="listitem" className={`ins-step ${i < idx ? 'done' : ''} ${i === idx ? 'current' : ''}`}
            aria-current={i === idx ? 'step' : undefined}>{s}</div>))}
      </div>
      {lc.blockers.length === 0
        ? <div className="ins-muted">Nothing blocks the next step.</div>
        : lc.blockers.map((b, i) => <div key={i} className="ins-row"><span className="ins-pill amber">{b.code}</span><span className="grow">{b.message}</span></div>)}
    </>
  );
}

const Link = ({ r, onOpen }) => (
  <div className="ins-row ins-clickable" onClick={() => onOpen(r.uid)}>
    <span className="ins-pill">{r.relationship || 'child'}</span><span className="mono">{r.id}</span>
    <span className="grow" title={r.title}>{r.title}</span>
    {r.suspect && <span className="ins-pill amber">suspect</span>}<span className="ins-pill">{r.status}</span>
  </div>
);

const STRATEGIC = ['theme', 'initiative', 'epic'];

/** Roll-up for a Theme, Initiative or Epic (MOD-10). */
function StrategicSummary({ uid }) {
  const [s, setS] = useState(null);
  useEffect(() => { let live = true; api.requirements.summary(uid).then(r => live && setS(r)).catch(() => {}); return () => { live = false; }; }, [uid]);
  if (!s) return null;
  return (
    <div role="region" aria-label="Summary">
      <h4>Summary</h4>
      <div className="ins-grid">
        <div className="ins-stat"><div className="ins-stat-value">{pct(s.progress_pct)}</div><div className="ins-stat-label">Complete</div></div>
        <div className="ins-stat"><div className="ins-stat-value">{s.descendants}</div><div className="ins-stat-label">Items below</div></div>
        <div className="ins-stat"><div className="ins-stat-value">{s.done_estimate}/{s.total_estimate}</div><div className="ins-stat-label">Estimate done</div></div>
        <div className="ins-stat"><div className="ins-stat-value">{s.open_tbds.length}</div><div className="ins-stat-label">Open TBDs</div></div>
        <div className="ins-stat"><div className="ins-stat-value">{s.validation.errors}/{s.validation.warnings}</div><div className="ins-stat-label">Errors / warnings</div></div>
      </div>
      {Object.entries(s.by_type).map(([t, counts]) => (
        <div className="ins-row" key={t}><span style={{ width: 80 }}>{t}</span>
          <span className="grow">{Object.entries(counts).map(([st, n]) => `${st.replace(/_/g, ' ')} ${n}`).join(', ')}</span></div>))}
    </div>
  );
}

export default function ItemInsight({ uid, draft, version }) {
  const { state, dispatch, toast } = useApp();
  const user = state.enums?._current_user || localStorage.getItem('reqtool:username') || 'user';
  const [data, setData] = useState({});
  const [error, setError] = useState(null);
  const [findings, setFindings] = useState([]);
  const [similar, setSimilar] = useState([]);
  const [ignored, setIgnored] = useState([]);
  const [reviewers, setReviewers] = useState('');
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    Promise.all([
      api.requirements.trace(uid), api.requirements.lifecycle(uid), api.requirements.progress(uid),
      api.requirements.impact(uid), api.requirements.reviewRequests(uid), api.requirements.approvals(uid),
    ]).then(([trace, lifecycle, progress, impact, reviews, approvals]) => {
      if (live) { setData({ trace, lifecycle, progress, impact, reviews, approvals }); setError(null); }
    }).catch(e => live && setError(e.message));
    return () => { live = false; };
  }, [uid, tick, state._lastCommit]);

  // Advisory quality rules and similar items while the text changes (never blocks a save).
  const title = draft?.title ?? '';
  const description = draft?.content?.description ?? '';
  const criteria = (draft?.content?.acceptance_criteria || draft?.acceptance_criteria || []).length;
  useEffect(() => {
    const t = setTimeout(() => {
      api.qualityCheck({ title, description, acceptance_criteria: criteria }).then(r => setFindings(r.findings)).catch(() => {});
      api.suggestDuplicates({ title, description, exclude_uid: uid }).then(r => setSimilar(r.suggestions)).catch(() => {});
    }, 400);
    return () => clearTimeout(t);
  }, [title, description, criteria, uid]);

  const open = (target) => dispatch({ type: 'SELECT', uid: target, artefactType: 'requirement' });
  const act = async (fn, ok) => { try { await fn(); if (ok) toast(ok, 'success'); setTick(n => n + 1); } catch (e) { toast(e.message, 'error'); } };
  if (error) return <div className="ins-error" role="alert">{error}</div>;
  if (!data.trace) return <div className="panel-loading"><div className="spinner" /></div>;
  const { trace, lifecycle, progress, impact, reviews, approvals } = data;
  const visibleSimilar = similar.filter(s => !ignored.includes(s.uid));

  return (
    <div>
      {STRATEGIC.includes(draft?.req_type) && <StrategicSummary uid={uid} />}
      <h4>Lifecycle</h4>
      <Lifecycle lc={lifecycle} />

      <h4>Traceability</h4>
      <div className="ins-muted">Gaps: {trace.gaps.length ? trace.gaps.join(', ') : 'none'} | children verified {pct(trace.coverage.children_verified_pct)}</div>
      <h5>Upstream ({trace.upstream.length})</h5>
      {trace.upstream.map(r => <Link key={r.uid + r.relationship} r={r} onOpen={open} />)}
      <h5>Downstream ({trace.downstream.length + trace.children.length})</h5>
      {trace.downstream.map(r => <Link key={r.uid + r.relationship} r={r} onOpen={open} />)}
      {trace.children.map(r => <Link key={r.uid} r={r} onOpen={open} />)}

      <h4>Progress and impact</h4>
      <div className="ins-row">
        <span style={{ width: 80 }}>Progress</span>
        <div className="grow"><Bar value={progress.progress_pct ?? progress.percent ?? progress.completion_pct ?? 0} label="Progress" /></div>
        <span>{pct(progress.progress_pct ?? progress.percent ?? progress.completion_pct ?? 0)}</span>
      </div>
      <details><summary className="ins-muted">Raw progress and impact data</summary>
        <pre style={{ fontSize: 11, overflow: 'auto' }}>{JSON.stringify({ progress, impact }, null, 2)}</pre></details>
      <button className="btn btn-ghost" onClick={() => act(async () => { const c = await api.requirements.clone(uid); open(c.uid); }, 'Cloned')}>Clone this item</button>

      <h4>Writing quality (advisory)</h4>
      {findings.length === 0 ? <div className="ins-muted">No suggestions.</div>
        : findings.map(f => <div key={f.code} className="ins-row"><span className="ins-pill amber">{f.code}</span><span className="grow">{f.message}</span></div>)}
      {visibleSimilar.length > 0 && <>
        <h5>Similar requirements</h5>
        {visibleSimilar.map(s => (
          <div key={s.uid} className="ins-row">
            <span className="mono">{s.id}</span><span className="grow" title={s.title}>{s.title}</span>
            <span className="ins-pill">{Math.round(s.similarity_score * 100)}%</span>
            <button className="btn btn-ghost" onClick={() => open(s.uid)}>Open</button>
            <button className="btn btn-ghost" onClick={() => setIgnored(l => [...l, s.uid])}>Ignore</button>
          </div>))}
      </>}

      <h4>Reviews and approvals</h4>
      <div style={{ display: 'flex', gap: 6 }}>
        <input aria-label="Reviewers" placeholder="Reviewers, comma separated" value={reviewers} onChange={e => setReviewers(e.target.value)} />
        <button className="btn btn-secondary" disabled={!reviewers.trim()}
          onClick={() => act(async () => { await api.requirements.requestReview(uid, reviewers.split(',').map(s => s.trim()).filter(Boolean)); setReviewers(''); }, 'Review requested')}>Request review</button>
        <button className="btn btn-primary" title="Approve exactly this version of the content"
          onClick={() => act(() => api.requirements.approve(uid, { approved_by: user, content_hash: approvals.current_hash }), 'Approved')}>Approve this version</button>
      </div>
      {reviews.map(r => (
        <div key={r.id} className="ins-row"><span className="grow">{r.reviewer} (v{r.version})</span>
          <span className={`ins-pill ${r.status === 'stale' ? 'amber' : r.status === 'approved' ? 'green' : ''}`}>{r.status === 'stale' ? 'content changed since requested' : r.status}</span></div>))}
      {approvals.approvals.map((a, i) => <div key={i} className="ins-muted">Approved by {a.approved_by} at v{a.version}</div>)}
    </div>
  );
}
