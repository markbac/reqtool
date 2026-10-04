#!/usr/bin/env python3
"""
scripts/build_docs.py
======================
Builds a well-structured, production-ready static documentation website
including an interactive OpenAPI 3.1 API Reference (Redoc) and full documentation suite
for deployment to GitHub Pages.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
import yaml
import markdown

ROOT = Path(__file__).parent.parent
DOCS_DIR = ROOT / "docs"
SITE_DIR = ROOT / "site"


SITE_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — reqtool Docs</title>
  <style>
    :root {{
      --bg-main: #0d1117;
      --bg-card: #161b22;
      --bg-nav: #161b22;
      --text-main: #c9d1d9;
      --text-heading: #f0f6fc;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --accent-hover: #79c0ff;
      --border: #30363d;
      --code-bg: #1f242c;
      --sidebar-width: 280px;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg-main);
      color: var(--text-main);
      line-height: 1.6;
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }}
    header.top-nav {{
      background: var(--bg-nav);
      border-bottom: 1px solid var(--border);
      height: 60px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--accent);
      text-decoration: none;
    }}
    .brand-icon {{ font-size: 1.4rem; }}
    .nav-links {{ display: flex; gap: 16px; align-items: center; }}
    .nav-link {{
      color: var(--text-main);
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 500;
      transition: color 0.15s;
    }}
    .nav-link:hover, .nav-link.active {{ color: var(--accent); }}
    .layout {{
      display: flex;
      flex: 1;
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
    }}
    aside.sidebar {{
      width: var(--sidebar-width);
      border-right: 1px solid var(--border);
      padding: 24px 16px;
      flex-shrink: 0;
      background: var(--bg-nav);
      height: calc(100vh - 60px);
      position: sticky;
      top: 60px;
      overflow-y: auto;
    }}
    .sidebar-section-title {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin: 16px 0 8px 12px;
      font-weight: 700;
    }}
    .sidebar-menu {{ list-style: none; }}
    .sidebar-item a {{
      display: block;
      padding: 8px 12px;
      border-radius: 6px;
      color: var(--text-main);
      text-decoration: none;
      font-size: 0.9rem;
      transition: background 0.15s, color 0.15s;
    }}
    .sidebar-item a:hover {{ background: rgba(88,166,255,0.1); color: var(--accent); }}
    .sidebar-item.active a {{ background: rgba(88,166,255,0.15); color: var(--accent); font-weight: 600; }}
    main.content {{
      flex: 1;
      padding: 40px 48px;
      max-width: 960px;
      overflow-x: auto;
    }}
    h1, h2, h3, h4, h5, h6 {{
      color: var(--text-heading);
      margin-top: 1.8em;
      margin-bottom: 0.6em;
      line-height: 1.3;
    }}
    h1 {{ font-size: 2.1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4em; margin-top: 0; }}
    h2 {{ font-size: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }}
    h3 {{ font-size: 1.25rem; }}
    p {{ margin-bottom: 1em; }}
    ul, ol {{ margin-bottom: 1em; padding-left: 24px; }}
    li {{ margin-bottom: 0.3em; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 2px 6px;
      font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, monospace;
      font-size: 0.88em;
    }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      overflow-x: auto;
      margin-bottom: 1.2em;
    }}
    pre code {{ background: none; border: none; padding: 0; font-size: 0.9em; }}
    blockquote {{
      border-left: 4px solid var(--accent);
      padding: 8px 16px;
      background: rgba(88,166,255,0.05);
      margin-bottom: 1em;
      border-radius: 0 4px 4px 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 1.5em;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 10px 14px;
      text-align: left;
    }}
    th {{ background: var(--bg-card); color: var(--text-heading); }}
    tr:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
    footer {{
      border-top: 1px solid var(--border);
      padding: 24px;
      text-align: center;
      font-size: 0.85rem;
      color: var(--text-muted);
      background: var(--bg-nav);
    }}
    @media (max-width: 860px) {{
      .layout {{ flex-direction: column; }}
      aside.sidebar {{ width: 100%; height: auto; position: static; }}
      main.content {{ padding: 24px 20px; }}
    }}
  </style>
</head>
<body>
  <header class="top-nav">
    <a href="index.html" class="brand">
      <span class="brand-icon">◈</span>
      <span>reqtool Documentation</span>
    </a>
    <nav class="nav-links">
      <a href="index.html" class="nav-link">Home</a>
      <a href="api-reference.html" class="nav-link">API Reference</a>
      <a href="https://github.com/markbac/reqtool/releases/latest" class="nav-link" target="_blank" style="color: var(--accent); font-weight: 600;">🚀 Download Release ↗</a>
      <a href="https://github.com/markbac/reqtool" class="nav-link" target="_blank">GitHub Repository ↗</a>
    </nav>
  </header>

  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-section-title">Documentation</div>
      <ul class="sidebar-menu">
        <li class="sidebar-item {active_index}"><a href="index.html">Overview &amp; Quickstart</a></li>
        <li class="sidebar-item {active_user_guide}"><a href="user-guide.html">User Guide</a></li>
        <li class="sidebar-item {active_product_datasheet}"><a href="product-datasheet.html">Product Datasheet</a></li>
        <li class="sidebar-item {active_architecture}"><a href="architecture.html">Architecture &amp; Design</a></li>
        <li class="sidebar-item {active_requirements_philosophy}"><a href="requirements-philosophy.html">Requirements Philosophy</a></li>
        <li class="sidebar-item {active_standalone_exe_guide}"><a href="standalone-exe-guide.html">Standalone Binaries Guide</a></li>
        <li class="sidebar-item {active_git_attachment_best_practices}"><a href="git-attachment-best-practices.html">Git LFS &amp; Attachments</a></li>
        <li class="sidebar-item {active_contributing}"><a href="contributing.html">Contributing</a></li>
      </ul>

      <div class="sidebar-section-title">Releases &amp; Downloads</div>
      <ul class="sidebar-menu">
        <li class="sidebar-item"><a href="reqtool-user-guide.pdf" download style="color: var(--accent); font-weight: 600;">📄 PDF User Guide (.pdf)</a></li>
        <li class="sidebar-item"><a href="https://github.com/markbac/reqtool/releases/latest" target="_blank">🚀 Latest Release Downloads ↗</a></li>
        <li class="sidebar-item"><a href="https://github.com/markbac/reqtool/releases/latest/download/reqtool-cli-windows-amd64.exe">🪟 Windows CLI (.exe)</a></li>
        <li class="sidebar-item"><a href="https://github.com/markbac/reqtool/releases/latest/download/reqtool-cli-linux-amd64">🐧 Linux CLI (amd64)</a></li>
        <li class="sidebar-item"><a href="https://github.com/markbac/reqtool/releases/latest/download/reqtool-documentation-and-user-guide.zip">📦 Docs Archive (.zip)</a></li>
      </ul>

      <div class="sidebar-section-title">API &amp; Specifications</div>
      <ul class="sidebar-menu">
        <li class="sidebar-item {active_api_reference}"><a href="api-reference.html">Interactive OpenAPI 3.1 Reference</a></li>
        <li class="sidebar-item"><a href="openapi.yaml" download>Download openapi.yaml</a></li>
        <li class="sidebar-item"><a href="openapi.json" download>Download openapi.json</a></li>
      </ul>
    </aside>

    <main class="content">
      {content}
    </main>
  </div>

  <footer>
    <p>reqtool &bull; Git-backed YAML Requirements Management &amp; OpenAPI 3.1 REST API &bull; Released under MIT License</p>
  </footer>
</body>
</html>
"""


REDOC_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>reqtool OpenAPI 3.1 REST API Specification</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    body { margin: 0; padding: 0; font-family: 'Inter', sans-serif; background: #0d1117; }
    header.top-nav {
      background: #161b22;
      border-bottom: 1px solid #30363d;
      height: 60px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      color: #c9d1d9;
    }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; color: #58a6ff; text-decoration: none; font-size: 1.1rem; }
    .nav-links a { color: #c9d1d9; text-decoration: none; font-size: 0.9rem; margin-left: 16px; }
    .nav-links a:hover { color: #58a6ff; }
  </style>
</head>
<body>
  <header class="top-nav">
    <a href="index.html" class="brand">
      <span>◈ reqtool OpenAPI 3.1 Specification</span>
    </a>
    <div class="nav-links">
      <a href="index.html">← Back to Docs</a>
      <a href="openapi.yaml" download>Download openapi.yaml</a>
      <a href="openapi.json" download>Download openapi.json</a>
    </div>
  </header>
  <div id="redoc-container"></div>
  <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
  <script>
    Redoc.init('openapi.json', {
      theme: {
        colors: {
          primary: { main: '#58a6ff' },
          success: { main: '#3fb950' },
          warning: { main: '#d29922' },
          error: { main: '#f85149' }
        },
        typography: {
          fontFamily: 'Inter, sans-serif',
          headings: { fontFamily: 'Inter, sans-serif' },
          code: { fontFamily: 'JetBrains Mono, monospace' }
        }
      },
      expandResponses: '200,201',
      requiredPropsFirst: true,
      hideDownloadButton: false
    }, document.getElementById('redoc-container'));
  </script>
</body>
</html>
"""


def build():
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    md = markdown.Markdown(extensions=["extra", "codehilite", "toc", "tables", "fenced_code"])

    docs_mapping = {
        "index.html": (ROOT / "README.md", "Overview & Quickstart", "active_index"),
        "user-guide.html": (DOCS_DIR / "USER_GUIDE.md", "User Guide", "active_user_guide"),
        "product-datasheet.html": (DOCS_DIR / "PRODUCT_DATASHEET.md", "Product Datasheet", "active_product_datasheet"),
        "architecture.html": (DOCS_DIR / "ARCHITECTURE.md", "Architecture & Design", "active_architecture"),
        "requirements-philosophy.html": (DOCS_DIR / "REQUIREMENTS_PHILOSOPHY.md", "Requirements Philosophy", "active_requirements_philosophy"),
        "standalone-exe-guide.html": (DOCS_DIR / "STANDALONE_EXE_GUIDE.md", "Standalone Binaries Guide", "active_standalone_exe_guide"),
        "git-attachment-best-practices.html": (DOCS_DIR / "GIT_ATTACHMENT_BEST_PRACTICES.md", "Git LFS & Attachments", "active_git_attachment_best_practices"),
        "contributing.html": (DOCS_DIR / "CONTRIBUTING.md", "Contributing", "active_contributing"),
    }

    # Render Markdown HTML pages
    for out_name, (src_file, title, active_key) in docs_mapping.items():
        if not src_file.exists():
            print(f"Skipping {src_file} (not found)")
            continue
        text = src_file.read_text(encoding="utf-8")
        html_body = md.convert(text)
        md.reset()

        active_flags = {
            "active_index": "", "active_user_guide": "", "active_product_datasheet": "",
            "active_architecture": "", "active_requirements_philosophy": "",
            "active_standalone_exe_guide": "", "active_git_attachment_best_practices": "",
            "active_contributing": "", "active_api_reference": ""
        }
        active_flags[active_key] = "active"

        full_html = SITE_TEMPLATE.format(
            title=title,
            content=html_body,
            **active_flags
        )
        (SITE_DIR / out_name).write_text(full_html, encoding="utf-8")
        print(f"Rendered: {out_name}")

    # Build PDF User Guide
    pdf_file = ROOT / "reqtool-user-guide.pdf"
    try:
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from generate_pdf_guide import build_pdf
        build_pdf()
        if pdf_file.exists():
            shutil.copy(pdf_file, SITE_DIR / "reqtool-user-guide.pdf")
            print("Copied reqtool-user-guide.pdf to site/")
    except Exception as exc:
        print(f"Warning: PDF generation failed or skipped: {exc}")

    # Copy openapi.yaml and write openapi.json
    openapi_yaml = ROOT / "openapi.yaml"
    if openapi_yaml.exists():
        shutil.copy(openapi_yaml, SITE_DIR / "openapi.yaml")
        spec_data = yaml.safe_load(openapi_yaml.read_text(encoding="utf-8"))
        (SITE_DIR / "openapi.json").write_text(json.dumps(spec_data, indent=2), encoding="utf-8")
        print("Copied openapi.yaml and generated openapi.json")

    # Render Redoc API Reference page
    (SITE_DIR / "api-reference.html").write_text(REDOC_TEMPLATE, encoding="utf-8")
    print("Rendered: api-reference.html (Redoc OpenAPI 3.1)")

    print(f"\nSite build complete! Generated files written to: {SITE_DIR.resolve()}")


if __name__ == "__main__":
    build()
