import { useState, useEffect } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';
import { Panel } from './Panel';

export function WebhooksPanel({ onClose }) {
  const { toast } = useApp();
  const [webhooks, setWebhooks] = useState([]);
  const [form, setForm] = useState({ url: '', events: ['status_changed','approved','comment_added'], secret: '', enabled: true });
  const [adding, setAdding] = useState(false);

  const load = () => api.webhooks.list().then(setWebhooks).catch(() => {});
  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!form.url.trim()) return;
    try {
      await api.webhooks.add({ ...form, url: form.url.trim(), secret: form.secret || null });
      setAdding(false); setForm({ url: '', events: ['status_changed','approved','comment_added'], secret: '', enabled: true });
      load(); toast('Webhook added', 'success');
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleDelete = async (idx) => {
    if (!confirm('Delete webhook?')) return;
    try { await api.webhooks.delete(idx); load(); toast('Deleted', 'info', 1500); }
    catch (err) { toast(err.message, 'error'); }
  };

  const ALL_EVENTS = ['status_changed','approved','comment_added','attachment_added'];

  return (
    <Panel title="Webhooks" onClose={onClose} width={520}>
      <div className="import-hint">
        Webhooks POST a JSON payload to your URL when events occur. Useful for Slack,
        Jira, ADO, or custom CI integrations. Set a secret to verify payloads with
        <code>X-Reqtool-Signature: sha256=...</code>.
      </div>

      {webhooks.map((wh, i) => (
        <div key={i} className="webhook-item">
          <div className="webhook-item-header">
            <span className="webhook-url mono">{wh.url}</span>
            <span className={`badge ${wh.enabled ? 'badge-approved' : 'badge-deprecated'}`}>
              {wh.enabled ? 'active' : 'disabled'}
            </span>
            <button className="btn btn-ghost" style={{ color: 'var(--accent-red)', fontSize: 11 }}
              onClick={() => handleDelete(i)}>✕</button>
          </div>
          <div className="webhook-events">
            {wh.events?.map(e => <span key={e} className="badge" style={{ fontSize: 9 }}>{e}</span>)}
          </div>
        </div>
      ))}

      {!adding && (
        <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }} onClick={() => setAdding(true)}>
          + Add webhook
        </button>
      )}
      {adding && (
        <div className="custom-field-def">
          <input value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
            placeholder="https://hooks.example.com/reqtool" />
          <input value={form.secret} onChange={e => setForm(f => ({ ...f, secret: e.target.value }))}
            placeholder="Signing secret (optional)" style={{ marginTop: 4 }} />
          <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {ALL_EVENTS.map(ev => (
              <label key={ev} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                <input type="checkbox"
                  checked={form.events.includes(ev)}
                  onChange={e => setForm(f => ({
                    ...f,
                    events: e.target.checked ? [...f.events, ev] : f.events.filter(x => x !== ev)
                  }))}
                  style={{ width: 'auto' }} />
                {ev}
              </label>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary" onClick={handleAdd} disabled={!form.url.trim()}>Add</button>
            <button className="btn btn-ghost" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}
    </Panel>
  );
}
