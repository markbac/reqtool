import { useState } from 'react';
import { useApp } from '../../AppContext';
import { Panel } from './Panel';
import { createAndOpen, templateBody } from '../../createItem';

export function TemplatesPanel({ onClose }) {
  const { state, dispatch, toast } = useApp();
  const { templates } = state;
  const [selected, setSelected] = useState(null);

  const applyTemplate = async (template) => {
    const item = await createAndOpen(templateBody(template), { dispatch, toast, hasProduct: !!state.activeProduct });
    if (item) { toast(`Created ${item.id} from '${template.label}'`, 'success'); onClose(); }
  };

  return (
    <Panel title="Requirement templates" onClose={onClose} width={500}>
      <div className="import-hint">
        Using a template creates a new requirement with these fields filled in. Edit
        <code>.reqtool/templates.yaml</code> to customise them.
      </div>
      {templates.length === 0 && <div className="text-muted">No templates defined.</div>}
      {templates.map(t => (
        <div
          key={t.id}
          className={`template-item ${selected === t.id ? 'template-item--selected' : ''}`}
          onClick={() => setSelected(t.id === selected ? null : t.id)}
        >
          <div className="template-item-header">
            <span className="template-label">{t.label}</span>
            <button className="btn btn-primary" style={{ fontSize: 11, padding: '3px 10px' }}
              onClick={e => { e.stopPropagation(); applyTemplate(t); }}>
              Use
            </button>
          </div>
          {t.description && <div className="template-desc">{t.description}</div>}
          {selected === t.id && t.fields && (
            <div className="template-fields">
              {Object.entries(t.fields).filter(([k]) => k !== 'content').map(([k, v]) => (
                <div key={k} className="template-field-row">
                  <span className="mono text-secondary" style={{ fontSize: 11 }}>{k}</span>
                  <span style={{ fontSize: 11 }}>{Array.isArray(v) ? v.join(', ') : String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </Panel>
  );
}
