"""
reqtool.features.diff
=====================
Requirement-level and field-level differences between two git refs (ENH-04, FEAT-02).
"""

from __future__ import annotations

from typing import Any

from reqtool.fileio import yaml_loads_safe
from reqtool.git_ops import run_git

IGNORED = {"history", "last_modified", "content_hash", "tool_version"}


def _show(root, ref: str, path: str) -> dict | None:
    code, text, _ = run_git(["show", f"{ref}:{path}"], root)
    data = yaml_loads_safe(text) if code == 0 else None
    return data if isinstance(data, dict) else None


def field_changes(old: dict, new: dict, prefix: str = "") -> list[dict[str, Any]]:
    """Changed fields, descending into nested mappings (``content.description``)."""
    out = []
    for key in sorted(set(old) | set(new)):
        if not prefix and key in IGNORED:
            continue
        a, b, name = old.get(key), new.get(key), f"{prefix}{key}"
        if isinstance(a, dict) and isinstance(b, dict):
            out.extend(field_changes(a, b, name + "."))
        elif a != b:
            out.append({"field": name, "old": a, "new": b})
    return out


def ref_diff(root, ref_a: str, ref_b: str, folder: str = "requirements") -> dict[str, Any]:
    """Added, removed and modified items between two refs, with the changed fields of each modified item."""
    code, out, err = run_git(["diff", "--name-status", "--no-renames", ref_a, ref_b, "--", folder], root)
    if code != 0:
        raise ValueError(err.strip() or "git diff failed")
    result: dict[str, Any] = {"from": ref_a, "to": ref_b, "added": [], "removed": [], "modified": []}
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        if not path.endswith(".yaml"):
            continue
        old = _show(root, ref_a, path) if status != "A" else None
        new = _show(root, ref_b, path) if status != "D" else None
        item = {"uid": (new or old or {}).get("uid") or path.rsplit("/", 1)[-1][:-5],
                "id": (new or old or {}).get("id"), "title": (new or old or {}).get("title", ""), "path": path}
        if status == "A":
            result["added"].append(item)
        elif status == "D":
            result["removed"].append(item)
        else:
            changes = field_changes(old or {}, new or {})
            if changes:
                result["modified"].append({**item, "fields": changes})
    result["summary"] = {k: len(result[k]) for k in ("added", "removed", "modified")}
    return result
