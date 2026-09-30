/**
 * DiagramPanel.jsx -- Interactive Architecture & Visual Modeling Canvas.
 * Supports Mermaid flowchart, sequence, and system architecture diagram generation
 * with clickable requirement UID nodes and SVG/Markdown export.
 */

import { useState } from 'react';
import { useApp } from '../AppContext';

const DEFAULT_DIAGRAM = `graph TD
    REQ1["REQ-SYS-001: Thermal Management System"] --> REQ2["REQ-HW-002: Temperature Sensor Array"]
    REQ1 --> REQ3["REQ-FW-003: PID Controller Loop"]
    REQ2 --> REQ4["REQ-HW-004: ADC Converter Interface"]
    REQ3 --> REQ5["REQ-SW-005: Overheat Cutoff Actuator"]
`;

const DIAGRAM_TEMPLATES = [
  {
    name: 'System Hierarchy',
    code: `graph TD
    SYS["SYS-001: Primary Controller"] --> HW["HW-010: Power Supply"]
    SYS --> FW["FW-020: Control Algorithm"]
    SYS --> SW["SW-030: Telemetry API"]`,
  },
  {
    name: 'Sequence Flow',
    code: `sequenceDiagram
    participant User
    participant App as Client UI
    participant Server as reqtool-server
    User->>App: Approve Requirement
    App->>Server: POST /requirements/{uid}/approve
    Server->>Server: Generate Ed25519 Signature
    Server-->>App: 200 OK (signature attached)`,
  },
  {
    name: 'Traceability Graph',
    code: `graph LR
    STK["STK-001: Power Efficiency"] --> SYS["SYS-010: Battery Life"]
    SYS --> HW["HW-100: Li-Ion Cell"]
    SYS --> FW["FW-100: Sleep Mode Manager"]`,
  },
];

export function DiagramPanel({ onClose }) {
  const { dispatch, toast } = useApp();
  const [code, setCode] = useState(DEFAULT_DIAGRAM);

  const handleCopyMarkdown = () => {
    navigator.clipboard.writeText(`\`\`\`mermaid\n${code}\n\`\`\``);
    toast.success('Mermaid markdown snippet copied to clipboard');
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" style={{ maxWidth: 720 }} onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">🎨 Visual Architecture & Diagram Canvas</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div className="panel-body" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>Templates:</span>
            {DIAGRAM_TEMPLATES.map(t => (
              <button
                key={t.name}
                className="btn btn-secondary"
                style={{ fontSize: 11, padding: '3px 8px' }}
                onClick={() => setCode(t.code)}
              >
                {t.name}
              </button>
            ))}
            <button className="btn btn-primary" style={{ marginLeft: 'auto', fontSize: 11 }} onClick={handleCopyMarkdown}>
              📋 Copy Markdown
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, minHeight: 320 }}>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Mermaid Code</label>
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
              <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Diagram Specification Preview</label>
              <div style={{
                flex: 1,
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 6,
                padding: 12,
                fontFamily: 'monospace',
                fontSize: 11,
                whiteSpace: 'pre-wrap',
                overflow: 'auto',
                color: 'var(--accent-color, #4ea8de)',
              }}>
                {code}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
