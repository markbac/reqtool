import { useState, useEffect } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';
import { Panel } from './Panel';

export function WorkflowPanel({ onClose }) {
  const { dispatch, toast } = useApp();
  const [wf, setWf] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.workflow.get().then(setWf).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.workflow.update(wf);
      dispatch({ type: 'SET_WORKFLOW', payload: updated });
      toast('Workflow saved', 'success');
    } catch (err) { toast(err.message, 'error'); }
    finally { setSaving(false); }
  };

  if (!wf) return <Panel title="Workflow" onClose={onClose}><div className="panel-loading"><div className="spinner" /></div></Panel>;

  return (
    <Panel title="Workflow configuration" onClose={onClose} width={500}>
      <div className="wf-hint">
        States and transitions define the lifecycle of requirements. The <strong>approved</strong> state
        triggers acceptance criteria validation. Edit <code>.reqtool/defaults/workflow.yaml</code> to
        change the defaults for new repositories.
      </div>

      <div className="metrics-section-title">States</div>
      {wf.states?.map((s) => (
        <div key={s.id} className="wf-state-row">
          <span className="wf-dot" style={{ background: s.colour }} />
          <span className="wf-state-id mono">{s.id}</span>
          <span className="wf-state-label">{s.label}</span>
          {s.terminal && <span className="badge" style={{ fontSize: 9 }}>terminal</span>}
          <span className="text-muted" style={{ fontSize: 11, marginLeft: 4 }}>→ {(wf.transitions?.[s.id] || []).join(', ') || '—'}</span>
        </div>
      ))}

      <div className="metrics-section-title" style={{ marginTop: 12 }}>Initial state</div>
      <select value={wf.initial} onChange={e => setWf(w => ({ ...w, initial: e.target.value }))}
        style={{ width: 200 }}>
        {wf.states?.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
      </select>

      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? <span className="spinner" /> : 'Save'}
        </button>
        <button className="btn btn-secondary" onClick={onClose}>Close</button>
      </div>
    </Panel>
  );
}
