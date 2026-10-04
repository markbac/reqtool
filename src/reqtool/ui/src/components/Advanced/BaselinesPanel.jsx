import { useState, useEffect } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';
import { Panel } from './Panel';

export function BaselinesPanel({ onClose }) {
  const { toast } = useApp();
  const [baselines, setBaselines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newMsg, setNewMsg] = useState('');
  const [diff, setDiff] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [fields, setFields] = useState(null);

  const load = () => {
    setLoading(true);
    api.baselines.list().then(setBaselines).catch(() => setBaselines([])).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    const body = { name: newName.trim(), message: newMsg.trim() || undefined };
    try {
      try {
        await api.baselines.create(body);
      } catch (err) {
        if (err.detail?.error !== 'dirty_working_tree') throw err;
        // The tag points at the last commit, so these edits would not be in it.
        const ok = confirm(`These items have uncommitted changes that will NOT be in the baseline:\n\n${err.detail.uncommitted.join(', ')}\n\nCreate the baseline anyway? (Cancel, commit, then try again.)`);
        if (!ok) return;
        await api.baselines.create({ ...body, allow_dirty: true });
      }
      toast(`Baseline '${newName}' created`, 'success');
      setCreating(false); setNewName(''); setNewMsg('');
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleDiff = async (name) => {
    setDiffLoading(true); setDiff(null);
    try {
      const d = await api.baselines.diff(name);
      setDiff(d);
      setFields(await api.baselines.fieldDiff(name).catch(() => null));
    } catch (err) { toast(err.message, 'error'); }
    finally { setDiffLoading(false); }
  };

  return (
    <Panel title="Baselines" onClose={onClose} width={540}>
      <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }}
        onClick={() => setCreating(v => !v)}>
        + Create baseline
      </button>

      {creating && (
        <div className="baseline-create-form">
          <input value={newName} onChange={e => setNewName(e.target.value)}
            placeholder="Name (e.g. v1.0-rc1)" onKeyDown={e => e.key === 'Enter' && handleCreate()} />
          <input value={newMsg} onChange={e => setNewMsg(e.target.value)}
            placeholder="Description (optional)" />
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreate} disabled={!newName.trim()}>Create</button>
            <button className="btn btn-secondary" onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </div>
      )}

      {loading && <div className="panel-loading"><div className="spinner" /></div>}
      {!loading && baselines.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          No baselines yet. Create one to snapshot the current requirements state.
        </div>
      )}

      {baselines.map(b => (
        <div key={b.name} className="baseline-item">
          <div className="baseline-item-header">
            <span className="baseline-name mono">{b.name.replace('baseline/', '')}</span>
            <span className="baseline-date text-muted">{b.date?.slice(0, 10)}</span>
            <button className="btn btn-ghost" style={{ fontSize: 11 }}
              onClick={() => handleDiff(b.name.replace('baseline/', ''))}>
              Diff vs now
            </button>
          </div>
          {b.message && <div className="baseline-msg text-secondary">{b.message}</div>}
          <div className="baseline-sha mono text-muted">{b.sha}</div>
        </div>
      ))}

      {diffLoading && <div className="panel-loading"><div className="spinner" /></div>}
      {diff && (
        <div className="baseline-diff">
          <div className="baseline-diff-title">Changes since baseline/{diff.baseline?.replace('baseline/', '')}</div>
          {diff.added?.length > 0 && (
            <div className="diff-group diff-group--added">
              <div className="diff-group-header">+ {diff.added.length} added</div>
              {diff.added.map(r => <div key={r.id} className="diff-item mono">{r.id}</div>)}
            </div>
          )}
          {diff.removed?.length > 0 && (
            <div className="diff-group diff-group--removed">
              <div className="diff-group-header">− {diff.removed.length} removed</div>
              {diff.removed.map(r => <div key={r.path} className="diff-item mono">{r.id || r.path}</div>)}
            </div>
          )}
          {diff.changed?.length > 0 && (
            <div className="diff-group diff-group--changed">
              <div className="diff-group-header">~ {diff.changed.length} changed</div>
              {diff.changed.map(r => (
                <div key={r.id} className="diff-item">
                  <span className="mono">{r.id}</span>
                  <span className="text-muted" style={{ fontSize: 10, marginLeft: 8 }}>v{r.current_version}</span>
                </div>
              ))}
            </div>
          )}
          {fields?.modified?.length > 0 && (
            <div className="diff-group diff-group--changed" role="region" aria-label="Field-level changes">
              <div className="diff-group-header">Field-level changes</div>
              {fields.modified.map(m => (
                <div key={m.uid} className="diff-item">
                  <span className="mono">{m.id}</span>
                  {m.fields.map(f => (
                    <div key={f.field} style={{ fontSize: 11, marginLeft: 12 }}>
                      <b>{f.field}</b>: <span className="text-muted">{JSON.stringify(f.old)}</span> → {JSON.stringify(f.new)}
                    </div>))}
                </div>))}
            </div>
          )}
          {!diff.added?.length && !diff.removed?.length && !diff.changed?.length && (
            <div style={{ color: 'var(--status-approved)', fontSize: 12 }}>✓ No changes since this baseline</div>
          )}
        </div>
      )}
    </Panel>
  );
}
