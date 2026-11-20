/**
 * DiagramPanel.jsx -- Diagrams: Mermaid in the browser, PlantUML on the server.
 * Supports Mermaid (Client-side) and PlantUML (Server-side via plantuml.jar)
 * flowchart, sequence, and component diagram generation with SVG preview.
 */

import { Panel } from './Advanced/Panel';
import { useEffect, useState } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';
import { safeSvg } from '../sanitize';

// An empty canvas says what to do (#377). With an item selected it starts from that item and its links.
const EMPTY_MERMAID = `%% Write a Mermaid diagram here, or select an item first to start from it and its links.
graph TD
`;
const EMPTY_PLANTUML = `@startuml
' Write a PlantUML diagram here, or select an item first to start from it and its links.
@enduml
`;

const label = (r) => `${r.id || r.uid}: ${(r.title || '').replace(/["\[\]]/g, "'")}`;
const node = (r) => (r.id || r.uid).replace(/[^A-Za-z0-9_]/g, '_');

/** A diagram of the item and what it links to, from its relationships. */
async function diagramFor(uid) {
  const item = await api.requirements.get(uid);
  const lines = ['graph TD', `    ${node(item)}["${label(item)}"]`];
  const pumlLines = ['@startuml', `[${label(item)}] as ${node(item)}`];
  for (const rel of item.relationships || []) {
    const target = rel.target?.uid || rel.uid || rel.ref;
    if (!target) continue;
    const other = await api.requirements.get(target).catch(() => null);
    if (!other) continue;
    lines.push(`    ${node(item)} -->|${(rel.type || '').replace(/_/g, ' ')}| ${node(other)}["${label(other)}"]`);
    pumlLines.push(`[${label(other)}] as ${node(other)}`, `${node(item)} --> ${node(other)} : ${(rel.type || '').replace(/_/g, ' ')}`);
  }
  pumlLines.push('@enduml');
  return { mermaid: lines.join('\n') + '\n', plantuml: pumlLines.join('\n') + '\n' };
}

export function DiagramPanel({ onClose }) {
  const { state, toast } = useApp();
  const [engine, setEngine] = useState('mermaid'); // 'mermaid' | 'plantuml'
  const [start, setStart] = useState({ mermaid: EMPTY_MERMAID, plantuml: EMPTY_PLANTUML });
  const [code, setCode] = useState(EMPTY_MERMAID);
  const [plantumlSvg, setPlantumlSvg] = useState('');
  const [rendering, setRendering] = useState(false);

  useEffect(() => {
    if (!state.selectedUid || state.selectedType !== 'requirement') return;
    let live = true;
    diagramFor(state.selectedUid).then(d => {
      if (!live) return;
      setStart(d);
      setCode(c => (c === EMPTY_MERMAID || c === EMPTY_PLANTUML ? (engine === 'mermaid' ? d.mermaid : d.plantuml) : c));
    }).catch(() => {});
    return () => { live = false; };
  }, [state.selectedUid]);

  const handleEngineChange = (newEngine) => {
    setEngine(newEngine);
    // Switch the starting text with the engine, unless it has been edited.
    if (code === start.mermaid || code === start.plantuml) setCode(start[newEngine]);
  };

  const handleRenderPlantUML = async () => {
    setRendering(true);
    try {
      const res = await api.render.plantuml(code);
      const svgText = await res.text();
      setPlantumlSvg(svgText);
      toast.success('PlantUML rendered via server backend');
    } catch (err) {
      toast.error('PlantUML render error: ' + err.message);
    } finally {
      setRendering(false);
    }
  };

  const handleCopyMarkdown = () => {
    const lang = engine === 'mermaid' ? 'mermaid' : 'puml';
    navigator.clipboard.writeText(`\`\`\`${lang}\n${code}\n\`\`\``);
    toast.success(`${engine === 'mermaid' ? 'Mermaid' : 'PlantUML'} snippet copied to clipboard`);
  };

  return (
    <Panel title="Diagrams" onClose={onClose} wide raw>

        <div className="panel-body" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Controls Bar */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: 4, background: 'var(--bg-secondary)', padding: 3, borderRadius: 6 }}>
              <button
                className={`btn ${engine === 'mermaid' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: 12, padding: '4px 10px' }}
                onClick={() => handleEngineChange('mermaid')}
              >
                Mermaid.js (Client-side)
              </button>
              <button
                className={`btn ${engine === 'plantuml' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: 12, padding: '4px 10px' }}
                onClick={() => handleEngineChange('plantuml')}
              >
                PlantUML (Backend plantuml.jar)
              </button>
            </div>

            {engine === 'plantuml' && (
              <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={handleRenderPlantUML} disabled={rendering}>
                {rendering ? 'Rendering SVG...' : '⚡ Render PlantUML SVG'}
              </button>
            )}

            <button className="btn btn-primary" style={{ marginLeft: 'auto', fontSize: 12 }} onClick={handleCopyMarkdown}>
              📋 Copy Code Snippet
            </button>
          </div>

          {/* Editor & Preview Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, minHeight: 360 }}>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                {engine === 'mermaid' ? 'Mermaid Diagram Definition' : 'PlantUML Source (@startuml)'}
              </label>
              <textarea
                value={code}
                onChange={e => setCode(e.target.value)}
                style={{
                  flex: 1,
                  fontFamily: 'monospace',
                  fontSize: 12,
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 6,
                  padding: 10,
                  resize: 'none',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                {engine === 'mermaid' ? 'Mermaid Specification View' : 'Server Rendered PlantUML SVG'}
              </label>
              <div style={{
                flex: 1,
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 6,
                padding: 12,
                overflow: 'auto',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                {engine === 'mermaid' ? (
                  <pre style={{
                    fontFamily: 'monospace',
                    fontSize: 12,
                    color: 'var(--accent-color, #4ea8de)',
                    margin: 0,
                    whiteSpace: 'pre-wrap',
                  }}>{code}</pre>
                ) : plantumlSvg ? (
                  <div dangerouslySetInnerHTML={{ __html: safeSvg(plantumlSvg) }} style={{ maxWidth: '100%', maxHeight: '100%' }} />
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
                    Click <b>⚡ Render PlantUML SVG</b> to execute backend <code className="mono">plantuml.jar</code>.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
    </Panel>
  );
}
