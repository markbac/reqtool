import { useEffect, useRef, useState } from 'react';

let loader = null;
let counter = 0;

/** Load Mermaid on first use, so it stays out of the main bundle. */
function loadMermaid() {
  if (!loader) {
    loader = import('mermaid').then(m => {
      const mermaid = m.default;
      mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'dark', flowchart: { htmlLabels: false } });
      return mermaid;
    });
  }
  return loader;
}

/**
 * Draws Mermaid source (made by the server) as an SVG. If Mermaid cannot load or the source cannot be drawn,
 * the source is shown as text instead.
 */
export function MermaidView({ source, title = 'Workflow diagram' }) {
  const host = useRef(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setFailed(false);
    if (!source) return undefined;
    loadMermaid()
      .then(mermaid => mermaid.render(`wfm-${++counter}`, source))
      .then(({ svg }) => { if (live && host.current) host.current.innerHTML = svg; })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [source]);

  if (!source) return null;
  if (failed) {
    return (
      <div className="mermaid-view" aria-label={title}>
        <div className="text-muted" style={{ fontSize: 11, marginBottom: 4 }}>The diagram could not be drawn. Mermaid source:</div>
        <pre className="mermaid-source" data-testid="mermaid-source">{source}</pre>
      </div>
    );
  }
  return <div className="mermaid-view" ref={host} role="img" aria-label={title} data-testid="mermaid-diagram" />;
}
