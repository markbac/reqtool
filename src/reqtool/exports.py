"""
reqtool.exports
===============
Export engine: Markdown (MkDocs/GitHub/plain), CSV, and JSX.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .store import Store

# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def _req_to_markdown(req: dict[str, Any], req_id_by_uid: Optional[dict[str, str]] = None) -> str:
    """Render a single requirement as Markdown (definition-list style, spec §11.2)."""
    lines = []
    rid = req.get("id", "")
    lines.append(f"## {rid} -- {req.get('title', '')}\n")

    content = req.get("content", {})
    if content.get("description"):
        lines.append("**Description**\n")
        lines.append(content["description"].strip())
        lines.append("")

    if content.get("rationale"):
        lines.append("**Rationale**\n")
        lines.append(content["rationale"].strip())
        lines.append("")

    if content.get("extended_description"):
        lines.append("**Extended Description**\n")
        lines.append(content["extended_description"].strip())
        lines.append("")

    # Metadata table
    meta_pairs = [
        ("Status",   req.get("status",  "")),
        ("Priority", req.get("priority", "")),
        ("Type",     req.get("req_type", "")),
        ("Domain",   req.get("domain",  "") or ""),
        ("Owner",    req.get("owner",   "") or ""),
        ("Version",  req.get("version", "")),
        ("Risk",     req.get("risk",    "") or ""),
    ]
    if req.get("safety_related"):
        meta_pairs.append(("Safety Classification", req.get("safety_classification") or "TBD"))
    meta_pairs += [
        ("Verification", req.get("verification_method", "")),
        ("Approval",     req.get("approval", {}).get("status", "")),
        ("Implementation", req.get("implementation", {}).get("status", "")),
    ]
    meta_lines = [f"- **{k}**: {v}" for k, v in meta_pairs if v]
    if meta_lines:
        lines.append("**Metadata**\n")
        lines.extend(meta_lines)
        lines.append("")

    # Acceptance criteria
    acs = req.get("acceptance_criteria", [])
    if acs:
        lines.append("**Acceptance Criteria**\n")
        for i, ac in enumerate(acs, 1):
            ac_text = ac.get("text", "").strip()
            ac_id = ac.get("id", "")
            lines.append(f"{i}. `{ac_id}` {ac_text}")
        lines.append("")

    # NFR constraints
    nfr = req.get("nfr", {})
    if nfr:
        lines.append("**NFR Constraints**\n")
        for k, v in nfr.items():
            lines.append(f"- `{k}`: {v}")
        lines.append("")

    # Constraints
    constraints = req.get("constraints", [])
    if constraints:
        lines.append("**Constraints**\n")
        for c in constraints:
            lines.append(f"- {c}")
        lines.append("")

    # Assumptions
    assumptions = req.get("assumptions", [])
    if assumptions:
        lines.append("**Assumptions**\n")
        for a in assumptions:
            lines.append(f"- {a}")
        lines.append("")

    # Relationships (cross-links using requirement IDs per spec §11.2)
    rels = req.get("relationships", [])
    if rels:
        lines.append("**Relationships**\n")
        for rel in rels:
            target_uid = rel.get("target", {}).get("uid", "")
            # Resolve UID to ID if available
            target_id = (req_id_by_uid or {}).get(target_uid, target_uid[:8] + "...") if target_uid else "?"
            lines.append(f"- `{rel.get('type', '')}` → [{target_id}](#{target_id.lower().replace('-', '-')})")
        lines.append("")

    # External links
    links = req.get("links", [])
    if links:
        lines.append("**External Links**\n")
        for link in links:
            ref = link.get("ref", "")
            title = link.get("title") or ref
            system = link.get("system", "")
            ltype = link.get("type", "")
            if ref.startswith("http"):
                lines.append(f"- `{system}/{ltype}` [{title}]({ref})")
            else:
                lines.append(f"- `{system}/{ltype}` `{ref}` {title}")
        lines.append("")

    return "\n".join(lines)



def export_markdown(
    store: "Store",
    product_id: Optional[str] = None,
    variant: Optional[str] = None,
    split_by: Optional[str] = None,
    flavor: str = "mkdocs",
) -> dict[str, str]:
    """
    Export requirements as Markdown.
    Returns a dict of filename -> content.
    Includes a mkdocs_nav.yml fragment when flavor == 'mkdocs'.
    """
    reqs = [r for r in store.requirements.values() if not r.get("deleted")]

    if product_id:
        tree = store.build_tree(product_id, variant)
        tree_uids: set[str] = set()

        def collect_uids(nodes: list) -> None:
            for node in nodes:
                if not node.get("_is_module_group"):
                    tree_uids.add(node["uid"])
                collect_uids(node.get("children", []))
        collect_uids(tree)
        reqs = [r for r in reqs if r.get("uid") in tree_uids]

    # Build UID -> ID map for cross-link resolution
    req_id_by_uid: dict[str, str] = {r["uid"]: r.get("id", "") for r in store.requirements.values()}

    split = split_by or store.config.export.markdown.split_by or "none"
    files: dict[str, str] = {}
    req_files: list[str] = []  # for mkdocs nav

    if split == "domain":
        by_domain: dict[str, list] = {}
        for req in reqs:
            domain = req.get("domain") or "other"
            by_domain.setdefault(domain, []).append(req)
        for domain, domain_reqs in sorted(by_domain.items()):
            fname = f"requirements-{domain}.md"
            content = "\n\n".join(
                _req_to_markdown(r, req_id_by_uid)
                for r in sorted(domain_reqs, key=lambda r: r.get("id", ""))
            )
            files[fname] = content
            req_files.append(fname)
    else:
        fname = "requirements.md"
        content = "\n\n".join(
            _req_to_markdown(r, req_id_by_uid)
            for r in sorted(reqs, key=lambda r: r.get("id", ""))
        )
        files[fname] = content
        req_files.append(fname)

    # Principles
    principles = [p for p in store.principles.values() if not p.get("deleted")]
    if principles:
        lines = []
        for p in sorted(principles, key=lambda x: x.get("id", "")):
            lines.append(f"## {p.get('id', '')} -- {p.get('title', '')}\n")
            c = p.get("content", {})
            for section, label in (
                ("description", "Statement"),
                ("rationale", "Rationale"),
                ("implications", "Implications"),
                ("exceptions", "Exceptions"),
            ):
                if c.get(section):
                    lines.append(f"**{label}**\n")
                    lines.append(c[section].strip())
                    lines.append("")
        files["principles.md"] = "\n".join(lines)

    # TBDs
    tbds = [t for t in store.tbds.values() if not t.get("deleted")]
    if tbds:
        lines = []
        for t in sorted(tbds, key=lambda x: x.get("id", "")):
            lines.append(f"## {t.get('id', '')} -- {t.get('title', '')}\n")
            c = t.get("content", {})
            if c.get("description"):
                lines.append(c["description"].strip())
                lines.append("")
            lines.append(f"- **Status**: {t.get('status', '')}")
            lines.append(f"- **Priority**: {t.get('priority', '')}")
            if t.get("owner"):
                lines.append(f"- **Owner**: {t['owner']}")
            if t.get("due"):
                lines.append(f"- **Due**: {t['due']}")
            if c.get("resolution"):
                lines.append("")
                lines.append(f"**Resolution**: {c['resolution']}")
            lines.append("")
        files["tbds.md"] = "\n".join(lines)

    # MkDocs nav fragment (spec §11.2)
    if flavor == "mkdocs":
        nav_lines = ["# Auto-generated by reqtool -- paste into mkdocs.yml nav section", "nav:"]
        for fname in req_files:
            label = fname.replace("requirements-", "").replace(".md", "").replace("-", " ").title()
            nav_lines.append(f"  - {label}: {fname}")
        if "principles.md" in files:
            nav_lines.append("  - Principles: principles.md")
        if "tbds.md" in files:
            nav_lines.append("  - Open Items (TBDs): tbds.md")
        files["mkdocs_nav.yml"] = "\n".join(nav_lines) + "\n"

    return files


def export_markdown_zip(store: "Store", **kwargs: Any) -> bytes:
    """Export Markdown files as a zip archive."""
    files = export_markdown(store, **kwargs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content.encode("utf-8"))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

_DEFAULT_CSV_FIELDS = [
    "id", "title", "status", "priority", "req_type", "domain",
    "owner", "verification_method", "approval.status", "parentId",
]


def _get_nested(data: dict, dotpath: str) -> Any:
    """Resolve a dotted path like 'approval.status' from a dict."""
    parts = dotpath.split(".", 1)
    val = data.get(parts[0])
    if len(parts) == 1:
        return val
    if isinstance(val, dict):
        return _get_nested(val, parts[1])
    return None


def _format_csv_value(data: dict, field: str) -> str:
    """Format a field value for CSV output per spec §11.3."""
    val = _get_nested(data, field)

    # Acceptance criteria: numbered plain-text list in single cell
    if field == "acceptance_criteria" and isinstance(val, list):
        parts = []
        for i, ac in enumerate(val, 1):
            text = ac.get("text", "").strip().replace("\n", " ")
            parts.append(f"{i}. {text}")
        return "\n".join(parts)

    # Relationships: semicolon-separated type:ID list
    if field == "relationships" and isinstance(val, list):
        return "; ".join(
            f"{r.get('type', '')}:{r.get('target', {}).get('uid', '')[:8]}"
            for r in val
        )

    # Links: semicolon-separated system/ref list
    if field == "links" and isinstance(val, list):
        return "; ".join(
            f"{lnk.get('system', '')}/{lnk.get('ref', '')}"
            for lnk in val
        )

    if isinstance(val, list):
        return "; ".join(str(v) for v in val)

    if val is None:
        return ""

    return str(val)


def export_csv(
    store: "Store",
    product_id: Optional[str] = None,
    variant: Optional[str] = None,
    fields: Optional[list[str]] = None,
) -> str:
    """Export requirements as CSV. Returns UTF-8 with BOM string."""
    field_list = fields or store.config.export.csv.include_fields or _DEFAULT_CSV_FIELDS
    delimiter = store.config.export.csv.delimiter or ","

    reqs = [r for r in store.requirements.values() if not r.get("deleted")]

    if product_id:
        tree = store.build_tree(product_id, variant)
        tree_uids: set[str] = set()

        def collect(nodes: list) -> None:
            for n in nodes:
                tree_uids.add(n["uid"])
                collect(n.get("children", []))
        collect(tree)
        reqs = [r for r in reqs if r.get("uid") in tree_uids]

    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM for Excel
    writer = csv.DictWriter(buf, fieldnames=field_list, delimiter=delimiter,
                            extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()

    for req in sorted(reqs, key=lambda r: r.get("id", "")):
        row: dict[str, Any] = {}
        for field in field_list:
            row[field] = _format_csv_value(req, field)
        writer.writerow(row)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# JSX export (stub -- generates a self-contained viewer component)
# ---------------------------------------------------------------------------

_JSX_TEMPLATE = """
// Auto-generated by reqtool {tool_version}
// Product: {product_id}
// Generated: {generated_at}
// DO NOT EDIT -- regenerate with: req export jsx

import React, {{ useState }} from "react";

const REQUIREMENTS = {requirements_json};
const PRINCIPLES = {principles_json};
const TBDS = {tbds_json};
const DOMAIN_COLOURS = {domain_colours_json};

function StatusBadge({{ status }}) {{
  const colours = {{
    draft: "#888", in_review: "#f5a623", approved: "#27ae60",
    deprecated: "#c0392b",
  }};
  return (
    <span style={{{{ background: colours[status] || "#ccc", color: "#fff",
      padding: "2px 8px", borderRadius: 4, fontSize: 11 }}}}>
      {{status}}
    </span>
  );
}}

function RequirementNode({{ req, depth = 0 }}) {{
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = req.children && req.children.length > 0;
  const colour = DOMAIN_COLOURS[req.domain] || "#4a5568";
  return (
    <div style={{{{ marginLeft: depth * 16 }}}}>
      <div
        style={{{{ display: "flex", alignItems: "center", gap: 8,
          padding: "4px 8px", cursor: hasChildren ? "pointer" : "default",
          borderLeft: `3px solid ${{colour}}`, marginBottom: 2 }}}}
        onClick={{() => hasChildren && setOpen(!open)}}
      >
        {{hasChildren && <span>{{open ? "▾" : "▸"}}</span>}}
        <span style={{{{ fontWeight: 600, color: colour }}}}>{{req.id}}</span>
        <span>{{req.title}}</span>
        <StatusBadge status={{req.status}} />
      </div>
      {{open && hasChildren && req.children.map(c => (
        <RequirementNode key={{c.uid}} req={{c}} depth={{depth + 1}} />
      ))}}
    </div>
  );
}}

export default function {component_name}() {{
  const [tab, setTab] = useState("requirements");
  const roots = REQUIREMENTS.filter(r => !r.parentId);

  return (
    <div style={{{{ fontFamily: "system-ui, sans-serif", maxWidth: 960, margin: "0 auto", padding: 16 }}}}>
      <div style={{{{ display: "flex", gap: 8, marginBottom: 16 }}}}>
        {{["requirements", "principles", "tbds"].map(t => (
          <button key={{t}} onClick={{() => setTab(t)}}
            style={{{{ padding: "6px 16px", borderRadius: 4, border: "1px solid #ccc",
              background: tab === t ? "#2563eb" : "#fff",
              color: tab === t ? "#fff" : "#333", cursor: "pointer" }}}}>
            {{t}}
          </button>
        ))}}
      </div>
      {{tab === "requirements" && (
        <div>
          {{roots.map(r => <RequirementNode key={{r.uid}} req={{r}} />)}}
        </div>
      )}}
      {{tab === "principles" && (
        <div>
          {{PRINCIPLES.map(p => (
            <div key={{p.uid}} style={{{{ borderBottom: "1px solid #eee", padding: "8px 0" }}}}>
              <strong>{{p.id}}</strong> -- {{p.title}}
              <p style={{{{ color: "#555", marginTop: 4 }}}}>{{p.content?.description}}</p>
            </div>
          ))}}
        </div>
      )}}
      {{tab === "tbds" && (
        <div>
          {{TBDS.map(t => (
            <div key={{t.uid}} style={{{{ borderBottom: "1px solid #eee", padding: "8px 0" }}}}>
              <strong>{{t.id}}</strong> <span style={{{{ color: t.status === "open" ? "#e74c3c" : "#27ae60" }}}}>{{t.status}}</span>
              <span style={{{{ marginLeft: 8 }}}}>{{t.title}}</span>
            </div>
          ))}}
        </div>
      )}}
    </div>
  );
}}
""".strip()


def _build_tree_flat(store: "Store", product_id: Optional[str], variant: Optional[str]) -> list[dict]:
    """Return requirements as a flat list with children arrays inlined."""
    tree = store.build_tree(product_id, variant)

    def flatten_with_children(nodes: list, parent_id: Optional[str] = None) -> list[dict]:
        result = []
        for node in nodes:
            entry = {
                "uid": node["uid"],
                "id": node["id"],
                "title": node["title"],
                "status": node["status"],
                "domain": node.get("domain"),
                "parentId": parent_id,
                "children": node.get("children", []),
            }
            result.append(entry)
        return result

    return flatten_with_children(tree)


def export_jsx(
    store: "Store",
    product_id: Optional[str] = None,
    variant: Optional[str] = None,
) -> str:
    """Generate a self-contained JSX viewer component."""
    from datetime import datetime, timezone

    cfg = store.config.export.jsx
    component_name = cfg.component_name or "RequirementsViewer"

    reqs_data = _build_tree_flat(store, product_id, variant)
    principles_data = (
        [{"uid": p["uid"], "id": p.get("id"), "title": p.get("title"),
          "content": p.get("content", {}), "status": p.get("status")}
         for p in store.principles.values() if not p.get("deleted")]
        if cfg.include_principles else []
    )
    tbds_data = (
        [{"uid": t["uid"], "id": t.get("id"), "title": t.get("title"), "status": t.get("status")}
         for t in store.tbds.values() if not t.get("deleted")]
        if cfg.include_tbds else []
    )

    # Build domain colour map from repo enums
    domain_colours: dict[str, str] = {}
    palette = [
        "#2563eb", "#16a34a", "#dc2626", "#ca8a04", "#9333ea",
        "#0891b2", "#ea580c", "#be185d", "#15803d", "#1d4ed8",
    ]
    for i, domain in enumerate(store.repo_enums.domain):
        domain_colours[domain] = palette[i % len(palette)]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return _JSX_TEMPLATE.format(
        tool_version="0.1.0",
        product_id=product_id or "all",
        generated_at=now,
        requirements_json=json.dumps(reqs_data, indent=2, default=str),
        principles_json=json.dumps(principles_data, indent=2, default=str),
        tbds_json=json.dumps(tbds_data, indent=2, default=str),
        domain_colours_json=json.dumps(domain_colours, indent=2),
        component_name=component_name,
    )
