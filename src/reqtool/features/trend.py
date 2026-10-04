"""
reqtool.features.trend
======================
Per-baseline metrics read from git, so a trend needs no stored history (FEAT-12).
"""

from __future__ import annotations

from typing import Any

from reqtool.fileio import yaml_loads_safe
from reqtool.git_ops import _run_git, git_list_tags, is_git_repo
from .insight import APPROVED_STATES, VERIFIED, _pct


def _files(root, tag: str, folder: str) -> list[tuple[str, str]]:
    code, listing, _ = _run_git(["ls-tree", "-r", "--name-only", tag, "--", folder], root)
    if code != 0:
        return []
    out = []
    for path in listing.splitlines():
        if path.endswith(".yaml"):
            code, text, _ = _run_git(["show", f"{tag}:{path}"], root)
            if code == 0:
                out.append((path, text))
    return out


def baseline_metrics(root, tag: str) -> dict[str, Any]:
    reqs = [d for _, t in _files(root, tag, "requirements") if isinstance(d := yaml_loads_safe(t), dict)
            and not d.get("deleted")]
    tbds = [d for _, t in _files(root, tag, "decisions") if isinstance(d := yaml_loads_safe(t), dict)
            and not d.get("deleted") and d.get("type") == "tbd" and d.get("status") in ("open", "in_progress")]
    total = len(reqs)
    _, when, _ = _run_git(["log", "-1", "--format=%cI", tag], root)
    return {
        "baseline": tag.removeprefix("baseline/"), "date": when.strip(), "requirements": total,
        "approved_pct": _pct(sum(1 for r in reqs if r.get("status") in APPROVED_STATES), total),
        "verified_pct": _pct(sum(1 for r in reqs if (r.get("verification") or {}).get("status") in VERIFIED), total),
        "traced_pct": _pct(sum(1 for r in reqs if r.get("relationships") or r.get("parentId")), total),
        "open_tbds": len(tbds),
    }


def trend(store) -> dict[str, Any]:
    """Metrics for every baseline, oldest first, with churn (items added, removed, changed) since the previous one."""
    if not is_git_repo(store.root):
        return {"points": []}
    tags = sorted(git_list_tags(store.root, prefix="baseline/"), key=lambda t: t.get("date") or t["name"])
    points, previous = [], None
    for tag in tags:
        point = baseline_metrics(store.root, tag["name"])
        if previous is not None:
            code, out, _ = _run_git(["diff", "--name-status", previous, tag["name"], "--", "requirements"], store.root)
            rows = [line.split("\t")[0][0] for line in out.splitlines() if line] if code == 0 else []
            point["churn"] = {"added": rows.count("A"), "removed": rows.count("D"), "changed": rows.count("M")}
        else:
            point["churn"] = {"added": point["requirements"], "removed": 0, "changed": 0}
        points.append(point)
        previous = tag["name"]
    return {"points": points}
