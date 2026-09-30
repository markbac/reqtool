/**
 * DiagramPanel.jsx -- Interactive Architecture & Visual Modeling Canvas.
 * Supports Mermaid (Client-side) and PlantUML (Server-side via plantuml.jar)
 * flowchart, sequence, and component diagram generation with SVG preview.
 */

import { useState } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';

const DEFAULT_MERMAID = `graph TD
    REQ1["REQ-SYS-001: Thermal Management System"] --> REQ2["REQ-HW-002: Temperature Sensor Array"]
    REQ1 --> REQ3["REQ-FW-003: PID Controller Loop"]
    REQ2 --> REQ4["REQ-HW-004: ADC Converter Interface"]
    REQ3 --> REQ5["REQ-SW-005: Overheat Cutoff Actuator"]
`;

const DEFAULT_PLANTUML = `@startuml
title Component Diagram - Thermal Control System

package "Sensors" {
  [REQ-HW-002: Temp Sensor] --> [ADC Converter]
}

package "Controller" {
  [REQ-FW-003: PID Loop] --> [Actuator Driver]
}

[ADC Converter] --> [REQ-FW-003: PID Loop]
[Actuator Driver] --> [REQ-SW-005: Cutoff Valve]
@enduml
`;

export function DiagramPanel({ onClose }) {
  const { toast } = useApp();
  const [engine, setEngine] = useState('mermaid'); // 'mermaid' | 'plantuml'
  const [code, setCode] = useState(DEFAULT_MERMAID);
  const [plantumlSvg, setPlantumlSvg] = useState('');
  const [rendering, setRendering] = useState(false);

  const handleEngineChange = (newEngine) => {
    setEngine(newEngine);
    if (newEngine === 'plantuml' && code === DEFAULT_MERMAID) {
      setCode(DEFAULT_PLANTUML);
    } else if (newEngine === 'mermaid' && code === DEFAULT_PLANTUML) {
      setCode(DEFAULT_MERMAID);
    }
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
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" style={{ maxWidth: 840 }} onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">🎨 Visual Architecture & Diagram Canvas</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div className="panel-body" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Controls Bar */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: 4, background: 'var(--bg-secondary)', padding: 3, borderRadius: 6 }}>
              <button
                className={`btn ${engine === 'mermaid' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: 11, padding: '4px 10px' }}
                onClick={() => handleEngineChange('mermaid')}
              >
                Mermaid.js (Client-side)
              </button>
              <button
                className={`btn ${engine === 'plantuml' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: 11, padding: '4px 10px' }}
                onClick={() => handleEngineChange('plantuml')}
              >
                PlantUML (Backend plantuml.jar)
              </button>
            </div>

            {engine === 'plantuml' && (
              <button className="btn btn-secondary" style={{ fontSize: 11 }} onClick={handleRenderPlantUML} disabled={rendering}>
                {rendering ? 'Rendering SVG...' : '⚡ Render PlantUML SVG'}
              </button>
            )}

            <button className="btn btn-primary" style={{ marginLeft: 'auto', fontSize: 11 }} onClick={handleCopyMarkdown}>
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
                    fontSize: 11,
                    color: 'var(--accent-color, #4ea8de)',
                    margin: 0,
                    whiteSpace: 'pre-wrap',
                  }}>{code}</pre>
                ) : plantumlSvg ? (
                  <div dangerouslySetInnerHTML={{ __html: plantumlSvg }} style={{ maxWidth: '100%', maxHeight: '100%' }} />
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
                    Click <b>⚡ Render PlantUML SVG</b> to execute backend <code className="mono">plantuml.jar</code>.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
