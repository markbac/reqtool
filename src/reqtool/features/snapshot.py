"""
reqtool.features.snapshot
=========================
A read-only static HTML site for stakeholders: search, traceability links, and a diff against the
previous baseline (FEAT-07). Runs in CI without a server or a login.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Optional

from reqtool.fileio import yaml_loads_safe
from reqtool.git_ops import run_git, git_list_tags, is_git_repo
from reqtool.graph import relationship_target
from .diff import ref_diff

STYLE = """body{font:16px/1.5 system-ui,sans-serif;margin:0;color:#1f2328;background:#fff}
main{max-width:60rem;margin:0 auto;padding:1rem}a{color:#0969da}header{border-bottom:1px solid #d0d7de;padding:.5rem 1rem}
input{width:100%;padding:.5rem;font-size:1rem;margin:.5rem 0}table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid #d0d7de;padding:.4rem;text-align:left}.tag{font-size:.8rem;border:1px solid #d0d7de;border-radius:1rem;padding:0 .5rem}
@media(prefers-color-scheme:dark){body{background:#0d1117;color:#e6edf3}a{color:#58a6ff}header,td,th{border-color:#30363d}}"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _requirements_at(store, ref: Optional[str]) -> dict[str, dict]:
    if ref is None:
        return {u: r for u, r in store.requirement_map().items() if not r.get("deleted")}
    code, listing, _ = run_git(["ls-tree", "-r", "--name-only", ref, "--", "requirements"], store.root)
    out = {}
    for path in listing.splitlines() if code == 0 else []:
        if not path.endswith(".yaml"):
            continue
        c, text, _ = run_git(["show", f"{ref}:{path}"], store.root)
        data = yaml_loads_safe(text) if c == 0 else None
        if isinstance(data, dict) and data.get("uid") and not data.get("deleted"):
            out[data["uid"]] = data
    return out


def _page(title: str, body: str, back: bool = True) -> str:
    nav = '<a href="index.html">All requirements</a>' if back else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{STYLE}</style></head>'
            f'<body><header>{nav}</header><main>{body}</main></body></html>')


def _detail(req: dict, reqs: dict[str, dict], incoming: dict[str, list[dict]]) -> str:
    def link(uid: str) -> str:
        r = reqs.get(uid)
        return f'<a href="{_e(uid)}.html">{_e(r.get("id") or uid)}</a> {_e(r.get("title", ""))}' if r else _e(uid)
    up = [f'<li>{_e(rel.get("type", ""))}: {link(t)}</li>' for rel in req.get("relationships") or []
          if (t := relationship_target(rel))]
    down = [f'<li>{_e(r.get("type", ""))}: {link(r["uid"])}</li>' for r in incoming.get(req["uid"], [])]
    content = req.get("content") or {}
    criteria = "".join(f"<li>{_e(c.get('text') if isinstance(c, dict) else c)}</li>"
                       for c in content.get("acceptance_criteria") or [])
    return _page(req.get("id") or req["uid"], (
        f'<h1>{_e(req.get("id"))} {_e(req.get("title"))}</h1><p><span class="tag">{_e(req.get("status"))}</span> '
        f'<span class="tag">v{_e(req.get("version"))}</span> <span class="tag">{_e(req.get("req_type"))}</span></p>'
        f'<p>{_e(content.get("description"))}</p>'
        + (f"<h2>Acceptance criteria</h2><ul>{criteria}</ul>" if criteria else "")
        + (f'<p>Parent: {link(req["parentId"])}</p>' if req.get("parentId") else "")
        + (f"<h2>Traces to</h2><ul>{''.join(up)}</ul>" if up else "")
        + (f"<h2>Traced from</h2><ul>{''.join(down)}</ul>" if down else "")))


def build_site(store, out_dir: Path, baseline: Optional[str] = None) -> dict[str, Any]:
    """Write the site to ``out_dir`` and return what was written. ``baseline`` is a baseline name (or None for HEAD files)."""
    ref = f"baseline/{baseline}" if baseline else None
    if ref and (not is_git_repo(store.root) or ref not in {t["name"] for t in git_list_tags(store.root, prefix="baseline/")}):
        raise ValueError(f"Baseline '{baseline}' not found")
    reqs = _requirements_at(store, ref)
    incoming: dict[str, list[dict]] = {}
    for uid, r in reqs.items():
        for rel in r.get("relationships") or []:
            target = relationship_target(rel)
            if target:
                incoming.setdefault(target, []).append({"uid": uid, "type": rel.get("type", "")})
    out_dir.mkdir(parents=True, exist_ok=True)
    for uid, r in reqs.items():
        (out_dir / f"{uid}.html").write_text(_detail(r, reqs, incoming), encoding="utf-8")

    previous = None
    if ref:
        tags = sorted(git_list_tags(store.root, prefix="baseline/"), key=lambda t: (t.get("date") or "", t["name"]))
        names = [t["name"] for t in tags]
        i = names.index(ref)
        previous = names[i - 1] if i else None
    change_html = ""
    if previous and ref:
        d = ref_diff(store.root, previous, ref)
        change_html = (f"<h2>Changes since {_e(previous.removeprefix('baseline/'))}</h2><p>{len(d['added'])} added, "
                       f"{len(d['removed'])} removed, {len(d['modified'])} modified</p><ul>"
                       + "".join(f"<li>Added {_e(i['id'])} {_e(i['title'])}</li>" for i in d["added"])
                       + "".join(f"<li>Removed {_e(i['id'])} {_e(i['title'])}</li>" for i in d["removed"])
                       + "".join(f"<li>Changed {_e(i['id'])}: {_e(', '.join(f['field'] for f in i['fields']))}</li>"
                                 for i in d["modified"]) + "</ul>")
    rows = "".join(f'<tr data-q="{_e(((r.get("id") or "") + " " + r.get("title", "") + " " + (r.get("content") or {}).get("description", "")).lower())}">'
                   f'<td><a href="{_e(uid)}.html">{_e(r.get("id") or uid)}</a></td><td>{_e(r.get("title"))}</td>'
                   f'<td>{_e(r.get("status"))}</td></tr>' for uid, r in sorted(reqs.items(), key=lambda kv: kv[1].get("id") or ""))
    script = ("const q=document.getElementById('q');q.addEventListener('input',()=>{const v=q.value.toLowerCase();"
              "document.querySelectorAll('tbody tr').forEach(r=>{r.hidden=!r.dataset.q.includes(v)})})")
    title = f"{store.config.repo_id or 'Requirements'}" + (f" - baseline {baseline}" if baseline else "")
    (out_dir / "index.html").write_text(_page(title, (
        f"<h1>{_e(title)}</h1><p>{len(reqs)} requirements</p>{change_html}"
        '<input id="q" type="search" placeholder="Search requirements" aria-label="Search requirements">'
        f"<table><thead><tr><th>ID</th><th>Title</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>"
        f"<script>{script}</script>"), back=False), encoding="utf-8")
    (out_dir / "data.json").write_text(json.dumps(
        [{"uid": u, "id": r.get("id"), "title": r.get("title"), "status": r.get("status")} for u, r in reqs.items()]),
        encoding="utf-8")
    return {"out": str(out_dir), "requirements": len(reqs), "baseline": baseline, "previous": previous}
