import { describe, it, expect } from 'vitest';
import { safeHtml, safeSvg } from '../sanitize';

describe('sanitize (SEC-17)', () => {
  it('strips script, handlers and javascript: URLs from html', () => {
    const out = safeHtml('<p onclick="x()">a</p><script>alert(1)</script><img src=x onerror=alert(1)><a href="javascript:alert(1)">l</a>').toLowerCase();
    for (const bad of ['<script', 'onclick', 'onerror', 'javascript:']) expect(out).not.toContain(bad);
    expect(out).toContain('<p>a</p>');
  });

  it('strips scripts and handlers from svg but keeps shapes', () => {
    const out = safeSvg('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script><rect width="10" height="10"/></svg>').toLowerCase();
    expect(out).not.toContain('<script');
    expect(out).not.toContain('onload');
    expect(out).toContain('<rect');
  });

  it('handles empty input', () => {
    expect(safeHtml(undefined)).toBe('');
    expect(safeSvg(null)).toBe('');
  });
});
