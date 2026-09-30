import React from 'react';

export function Panel({ title, onClose, width = 520, children }) {
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" style={{ width }} onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">{title}</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="panel-body">
          {children}
        </div>
      </div>
    </div>
  );
}
