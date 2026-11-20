/**
 * Panel.jsx -- The one container for a screen (#374).
 *
 * Inside a page (an area of the left-hand menu) it renders in place, filling the page. Anywhere else it is the
 * standard drawer: 480 px, or 720 px for wide content, a header with the title and close, a scrolling body and an
 * optional sticky footer for actions. Escape and the backdrop close it; focus is kept inside and given back.
 */

import { createContext, useContext, useEffect, useRef } from 'react';

export const PageContext = createContext(false);

/** Render the children as pages: every Panel inside fills the page instead of opening a drawer. */
export function InPage({ children }) {
  return <PageContext.Provider value={true}>{children}</PageContext.Provider>;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Panel({ title, onClose, width, wide, footer, raw, actions, children }) {
  const inPage = useContext(PageContext);
  if (inPage) {
    return (
      <section className={`page-panel ${raw ? 'page-panel--raw' : ''}`} aria-label={typeof title === 'string' ? title : undefined}>
        {actions && <div className="page-panel-actions">{actions}</div>}
        {raw ? children : <div className="page-panel-body">{children}</div>}
        {footer && <div className="page-panel-footer">{footer}</div>}
      </section>
    );
  }
  return <Drawer title={title} onClose={onClose} wide={wide || (width && width > 560)} footer={footer} raw={raw}
    actions={actions}>{children}</Drawer>;
}

export function Drawer({ title, onClose, wide, footer, raw, actions, children }) {
  const ref = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {   // once per opening: callers pass a new onClose on every render
    const before = document.activeElement;
    const first = ref.current?.querySelector(FOCUSABLE);
    (first || ref.current)?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); close.current?.(); return; }
      if (e.key !== 'Tab' || !ref.current) return;
      const items = [...ref.current.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
      if (!items.length) return;
      const [head, tail] = [items[0], items[items.length - 1]];
      if (e.shiftKey && document.activeElement === head) { e.preventDefault(); tail.focus(); }
      else if (!e.shiftKey && document.activeElement === tail) { e.preventDefault(); head.focus(); }
    };
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      if (before && typeof before.focus === 'function') before.focus();
    };
  }, []);
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div ref={ref} className={`side-panel ${wide ? 'side-panel--wide' : ''}`} role="dialog" aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined} tabIndex={-1} onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">{title}</span>
          <div className="side-panel-header-actions">
            {actions}
            <button className="btn btn-ghost" onClick={onClose} aria-label="Close">✕</button>
          </div>
        </div>
        {raw ? children : <div className="panel-body">{children}</div>}
        {footer && <div className="side-panel-footer">{footer}</div>}
      </div>
    </div>
  );
}
