import { useState, useEffect } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';
import { Panel } from './Panel';

export function CustomFieldsPanel({ onClose }) {
  const { toast } = useApp();
  const [schema, setSchema] = useState([]);
  const [saving, setSaving] = useState(false);
  const TYPES = ['string','number','boolean','select','multiselect','date'];

  useEffect(() => {
    api.customFields.schema().then(setSchema).catch(() => {});
  }, []);

  const addField = () => setSchema(s => [...s, {
    key: '', label: '', type: 'string', options: [], required: false, description: '', default: null,
    applies_to: ['requirement'],
  }]);

  const updateField = (i, patch) => setSchema(s => s.map((f, j) => j === i ? { ...f, ...patch } : f));
  const removeField = (i) => setSchema(s => s.filter((_, j) => j !== i));

  const save = async () => {
    const keys = schema.map(f => f.key.trim());
    if (keys.some(k => !k)) { toast('All fields must have a key', 'error'); return; }
    if (new Set(keys).size !== keys.length) { toast('Field keys must be unique', 'error'); return; }
    setSaving(true);
    try {
      await api.customFields.save(schema.map(f => ({ ...f, key: f.key.trim() })));
      toast('Custom field schema saved', 'success');
    } catch (err) { toast(err.message, 'error'); }
    finally { setSaving(false); }
  };

  return (
    <Panel title="Custom field schema" onClose={onClose} width={580}>
      <div className="import-hint">
        Define project-specific fields that appear on requirements. Values are stored in
        <code> custom_fields.key</code> in each YAML file. Schema lives in
        <code>.reqtool/custom_fields.yaml</code>.
      </div>

      {schema.map((field, i) => (
        <div key={i} className="custom-field-def">
          <div className="custom-field-def-row">
            <input value={field.key} onChange={e => updateField(i, { key: e.target.value })}
              placeholder="key (snake_case)" style={{ flex: 1 }} />
            <input value={field.label} onChange={e => updateField(i, { label: e.target.value })}
              placeholder="Display label" style={{ flex: 1 }} />
            <select value={field.type} onChange={e => updateField(i, { type: e.target.value })} style={{ flex: '0 0 100px' }}>
              {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, flexShrink: 0 }}>
              <input type="checkbox" checked={field.required} onChange={e => updateField(i, { required: e.target.checked })} style={{ width: 'auto' }} />
              Required
            </label>
            <button className="btn btn-ghost" style={{ color: 'var(--accent-red)', fontSize: 11 }} onClick={() => removeField(i)}>✕</button>
          </div>
          {(field.type === 'select' || field.type === 'multiselect') && (
            <input
              value={(field.options || []).join(', ')}
              onChange={e => updateField(i, { options: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
              placeholder="Options (comma-separated)"
              style={{ marginTop: 4, fontSize: 12 }}
            />
          )}
          <input value={field.description || ''} onChange={e => updateField(i, { description: e.target.value })}
            placeholder="Description (shown as hint)" style={{ marginTop: 4, fontSize: 12 }} />
        </div>
      ))}

      <button className="btn btn-secondary" onClick={addField}>+ Add field</button>

      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? <span className="spinner" /> : 'Save schema'}
        </button>
        <button className="btn btn-ghost" onClick={onClose}>Close</button>
      </div>
    </Panel>
  );
}
