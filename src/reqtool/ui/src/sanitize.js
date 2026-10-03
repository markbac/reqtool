import DOMPurify from 'dompurify';

/** Sanitise untrusted HTML (markdown output) before it goes into the DOM. */
export function safeHtml(html) {
  return DOMPurify.sanitize(html ?? '', { USE_PROFILES: { html: true } });
}

/** Sanitise untrusted SVG (diagram renderer output). Strips scripts and handlers. */
export function safeSvg(svg) {
  return DOMPurify.sanitize(svg ?? '', { USE_PROFILES: { svg: true, svgFilters: true } });
}
