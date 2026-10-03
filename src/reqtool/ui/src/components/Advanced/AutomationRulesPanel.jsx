import { useState, useEffect } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';
import { ruleErrors, newRule, cleanRule } from '../../automationRules';

export function AutomationRulesPanel({ onClose }) {
  const { toast } = useApp();
  const [rules, setRules] = useState(null);
  const [schema, setSchema] = useState(null);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([api.automation.getRules(), api.automation.schema()])
      .then(([data, sch]) => { setRules(Array.isArray(data) ? data : []); setSchema(sch); })
      .catch(err => toast(err.message, 'error'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.automation.updateRules(rules.map(cleanRule));
      setErrors({});
      setRules(await api.automation.getRules());
      toast('Automation rules saved', 'success');
    } catch (err) {
      const perRule = ruleErrors(err);
      setErrors(perRule);
      toast(Object.keys(perRule).length ? 'Some rules are invalid -- see the messages under each rule' : err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const addRule = () => setRules(prev => [...(prev || []), newRule(schema)]);
  const updateRule = (idx, patch) => setRules(prev => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  const deleteRule = (idx) => { setRules(prev => prev.filter((_, i) => i !== idx)); setErrors({}); };

  const conditionPairs = (rule) => Object.entries(rule.condition || {});
  const setCondition = (idx, rule, pairs) => updateRule(idx, { condition: Object.fromEntries(pairs.filter(([k]) => k !== '')) });

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel side-panel--wide" onClick={e => e.stopPropagation()} style={{ width: 620 }}>
        <div className="side-panel-header">
          <span className="side-panel-title">Automation Rules Manager</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving || !rules || !schema}>
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
              Event-driven rules stored in <code>.reqtool/automation_rules.yaml</code>. A rule runs its action when the
              event happens and every condition matches the event (for example <code>req_type</code> = <code>safety</code>).
            </p>

            {(rules || []).length === 0 && (
              <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)' }}>No automation rules configured yet.</div>
            )}

            {(rules || []).map((rule, idx) => {
              const act = schema?.actions.find(a => a.id === rule.action);
              return (
                <div key={rule.id || idx} data-testid="automation-rule" style={{
                  background: 'var(--bg-secondary)', border: `1px solid ${errors[idx] ? 'var(--accent-red)' : 'var(--border)'}`,
                  borderRadius: 6, padding: 12, marginBottom: 12,
                }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                    <input type="checkbox" aria-label="Enabled" checked={rule.enabled !== false}
                      onChange={e => updateRule(idx, { enabled: e.target.checked })} style={{ width: 'auto' }} />
                    <input aria-label="Rule name" value={rule.name || ''} onChange={e => updateRule(idx, { name: e.target.value })}
                      style={{ fontWeight: 600, flex: 1 }} placeholder="Rule name" />
                    <button className="btn btn-ghost" aria-label="Delete rule" style={{ color: 'var(--accent-red)' }} onClick={() => deleteRule(idx)}>✕</button>
                  </div>

                  <div className="field-row">
                    <div className="field-group" style={{ flex: 1 }}>
                      <label className="field-label">Trigger event</label>
                      <select aria-label="Trigger event" value={rule.event} onChange={e => updateRule(idx, { event: e.target.value })}>
                        {!schema.events.some(e => e.id === rule.event) && <option value={rule.event}>{rule.event} (unsupported)</option>}
                        {schema.events.map(e => <option key={e.id} value={e.id}>{e.label}</option>)}
                      </select>
                    </div>
                  </div>

                  <div style={{ marginTop: 8 }}>
                    <label className="field-label">Conditions (all must match)</label>
                    {conditionPairs(rule).map(([k, v], cIdx, all) => (
                      <div key={cIdx} style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                        <input aria-label="Condition field" value={k} placeholder="field (e.g. req_type)" style={{ flex: 1 }}
                          onChange={e => setCondition(idx, rule, all.map((p, i) => (i === cIdx ? [e.target.value, p[1]] : p)))} />
                        <input aria-label="Condition value" value={String(v ?? '')} placeholder="value" style={{ flex: 1 }}
                          onChange={e => setCondition(idx, rule, all.map((p, i) => (i === cIdx ? [p[0], e.target.value] : p)))} />
                        <button className="btn btn-ghost" aria-label="Remove condition"
                          onClick={() => setCondition(idx, rule, all.filter((_, i) => i !== cIdx))}>✕</button>
                      </div>
                    ))}
                    <button className="btn btn-ghost" style={{ marginTop: 4 }}
                      onClick={() => updateRule(idx, { condition: { ...(rule.condition || {}), [`field${conditionPairs(rule).length + 1}`]: '' } })}>
                      + Add condition
                    </button>
                  </div>

                  <div style={{ marginTop: 8 }}>
                    <label className="field-label">Action</label>
                    <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                      <select aria-label="Action" value={rule.action} style={{ width: 150 }} onChange={e => updateRule(idx, { action: e.target.value })}>
                        {!act && <option value={rule.action}>{rule.action} (unsupported)</option>}
                        {schema.actions.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
                      </select>
                      {act?.requires.includes('target_field') && (
                        <input aria-label="Target field" value={rule.target_field || ''} placeholder="field (e.g. owner)" style={{ flex: 1 }}
                          onChange={e => updateRule(idx, { target_field: e.target.value })} />
                      )}
                      {act?.requires.includes('target_value') && (
                        <input aria-label="Target value" value={rule.target_value || ''} placeholder="value" style={{ flex: 1 }}
                          onChange={e => updateRule(idx, { target_value: e.target.value })} />
                      )}
                    </div>
                  </div>

                  {errors[idx]?.map((m, i) => (
                    <div key={i} role="alert" style={{ color: 'var(--accent-red)', fontSize: 12, marginTop: 6 }}>{m}</div>
                  ))}
                </div>
              );
            })}

            <button className="btn btn-secondary" style={{ width: '100%' }} onClick={addRule} disabled={!schema}>
              + Add Automation Rule
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
