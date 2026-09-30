import { useState, useEffect } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';

export function AutomationRulesPanel({ onClose }) {
  const { toast } = useApp();
  const [rules, setRules] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.automation.getRules()
      .then(data => setRules(data))
      .catch(err => toast(err.message, 'error'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.automation.updateRules(rules);
      toast('Automation rules saved', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const addRule = () => {
    const newRule = {
      name: `Rule ${Date.now().toString().slice(-4)}`,
      enabled: true,
      event: 'requirement.created',
      actions: [{ type: 'set_field', field: 'status', value: 'draft' }]
    };
    setRules(prev => ({
      ...prev,
      rules: [...(prev?.rules || []), newRule]
    }));
  };

  const updateRule = (idx, patch) => {
    setRules(prev => {
      const updated = [...(prev?.rules || [])];
      updated[idx] = { ...updated[idx], ...patch };
      return { ...prev, rules: updated };
    });
  };

  const deleteRule = (idx) => {
    setRules(prev => ({
      ...prev,
      rules: (prev?.rules || []).filter((_, i) => i !== idx)
    }));
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel side-panel--wide" onClick={e => e.stopPropagation()} style={{ width: 620 }}>
        <div className="side-panel-header">
          <span className="side-panel-title">Automation Rules Manager</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving || !rules}>
              {saving ? <span className="spinner" /> : 'Save Rules'}
            </button>
            <button className="btn btn-ghost" onClick={onClose}>✕</button>
          </div>
        </div>

        {loading ? (
          <div className="panel-body"><div className="panel-loading"><div className="spinner" /></div></div>
        ) : (
          <div className="panel-body">
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Configure event-driven workflow automation triggers and actions (stored in <code>automation_rules.yaml</code>).
            </p>

            {(rules?.rules || []).length === 0 && (
              <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)' }}>No automation rules configured yet.</div>
            )}

            {(rules?.rules || []).map((rule, idx) => (
              <div key={idx} style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: 12,
                marginBottom: 12
              }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                  <input
                    type="checkbox"
                    checked={rule.enabled !== false}
                    onChange={e => updateRule(idx, { enabled: e.target.checked })}
                    style={{ width: 'auto' }}
                  />
                  <input
                    value={rule.name || ''}
                    onChange={e => updateRule(idx, { name: e.target.value })}
                    style={{ fontWeight: 600, flex: 1 }}
                    placeholder="Rule name"
                  />
                  <button className="btn btn-ghost" style={{ color: 'var(--accent-red)' }} onClick={() => deleteRule(idx)}>✕</button>
                </div>

                <div className="field-row">
                  <div className="field-group" style={{ flex: 1 }}>
                    <label className="field-label">Trigger Event</label>
                    <select value={rule.event || 'requirement.created'} onChange={e => updateRule(idx, { event: e.target.value })}>
                      <option value="requirement.created">requirement.created</option>
                      <option value="requirement.updated">requirement.updated</option>
                      <option value="requirement.approved">requirement.approved</option>
                      <option value="attachment.added">attachment.added</option>
                      <option value="comment.added">comment.added</option>
                    </select>
                  </div>
                </div>

                <div style={{ marginTop: 8 }}>
                  <label className="field-label">Actions</label>
                  {(rule.actions || []).map((act, aIdx) => (
                    <div key={aIdx} style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                      <input
                        value={act.type || 'set_field'}
                        onChange={e => {
                          const actions = [...rule.actions];
                          actions[aIdx] = { ...act, type: e.target.value };
                          updateRule(idx, { actions });
                        }}
                        style={{ width: 110 }}
                        placeholder="action type"
                      />
                      <input
                        value={act.field || ''}
                        onChange={e => {
                          const actions = [...rule.actions];
                          actions[aIdx] = { ...act, field: e.target.value };
                          updateRule(idx, { actions });
                        }}
                        style={{ flex: 1 }}
                        placeholder="field (e.g. status)"
                      />
                      <input
                        value={act.value || ''}
                        onChange={e => {
                          const actions = [...rule.actions];
                          actions[aIdx] = { ...act, value: e.target.value };
                          updateRule(idx, { actions });
                        }}
                        style={{ flex: 1 }}
                        placeholder="value"
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <button className="btn btn-secondary" style={{ width: '100%' }} onClick={addRule}>
              + Add Automation Rule
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
