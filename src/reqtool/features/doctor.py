"""
reqtool.features.doctor
=======================
``req doctor``: configuration, secrets hygiene, dependencies, hierarchy sanity and stray files (FEAT-11).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

SECRET_PATTERNS = (".reqtool/.secret_key", ".reqtool/users.yaml", ".reqtool/api_keys.yaml")
DEPENDENCIES = ("fastapi", "pydantic", "ruamel.yaml", "watchdog", "jwt", "reportlab")
ARTEFACT_DIRS = ("requirements", "principles", "decisions", "modules", "products")


def _check(level: str, code: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message}


def run_doctor(store) -> dict[str, Any]:
    root: Path = store.root
    out: list[dict[str, str]] = []

    # configuration
    for name in ("config.yaml", "workflow.yaml", "enums.yaml"):
        if not (root / ".reqtool" / name).exists() and not (root / name).exists():
            out.append(_check("warning", "config_missing", f"{name} not found: built-in defaults are in use"))

    # secrets must not be committed
    gitignore = root / ".gitignore"
    ignored = gitignore.read_text(encoding="utf-8", errors="replace").splitlines() if gitignore.exists() else []
    ignored_set = {line.strip().lstrip("/") for line in ignored}
    for pattern in SECRET_PATTERNS:
        if (root / pattern).exists() and not (pattern in ignored_set or ".reqtool/" in ignored_set
                                               or ".reqtool" in ignored_set):
            out.append(_check("error", "secret_not_ignored", f"{pattern} exists but is not in .gitignore"))

    # dependencies
    for dep in DEPENDENCIES:
        try:
            present = importlib.util.find_spec(dep) is not None
        except (ImportError, ValueError):
            present = False
        if not present:
            out.append(_check("warning", "dependency_missing", f"Python package '{dep}' is not installed"))

    # hierarchy sanity
    types = set(store.hierarchy.types)
    live = {u: r for u, r in store.requirement_map().items() if not r.get("deleted")}
    for uid, r in live.items():
        label = r.get("id") or uid
        if types and r.get("req_type") and r["req_type"] not in types:
            out.append(_check("warning", "unknown_type", f"{label} has unknown type '{r['req_type']}'"))
        parent = r.get("parentId")
        if parent and parent not in live:
            out.append(_check("error", "missing_parent", f"{label} points at parent {parent} which does not exist"))
        seen, cur = {uid}, parent
        while cur and cur in live:
            if cur in seen:
                out.append(_check("error", "parent_cycle", f"{label} is part of a parent cycle"))
                break
            seen.add(cur)
            cur = live[cur].get("parentId")

    # orphaned and misnamed files
    known = {*store.requirement_map(), *store.principle_map(), *store.decision_map()}
    for d in ARTEFACT_DIRS:
        folder = root / d
        if not folder.is_dir():
            continue
        for f in folder.glob("*.yaml"):
            if d in ("requirements", "principles", "decisions") and f.stem not in known:
                out.append(_check("warning", "orphan_file", f"{d}/{f.name} was not loaded as an artefact"))

    # operating mode
    from reqtool.git_ops import dirty_paths, is_git_repo, remotes
    from reqtool.modes import resolve_mode
    operating_mode = resolve_mode(store.config.mode)
    if operating_mode != "server" and is_git_repo(root):
        from reqtool.identity import git_identity, tool_identity
        me = git_identity(root)
        if me is None:
            out.append(_check("warning", "no_git_identity",
                              "No git identity is configured, so commits will be refused: set user.name and user.email"))
        elif me == tool_identity(store.config):
            out.append(_check("warning", "tool_git_identity",
                              f"Commits are attributed to the tool identity ({me}): set your own user.name and "
                              "user.email (`git config --local --unset user.name` removes one an older release wrote)"))
    if operating_mode == "shared-repo":
        if not is_git_repo(root):
            out.append(_check("error", "not_git_repo", "shared-repo mode needs a git repository"))
        elif not remotes(root):
            out.append(_check("error", "no_remote", "shared-repo mode needs a git remote: run `git remote add origin <url>`"))
        if is_git_repo(root):
            from reqtool.merge import is_installed, missing_attributes
            if missing_attributes(root):
                out.append(_check("warning", "merge_attributes_missing",
                                  "reqtool's merge driver is not declared in .gitattributes: run `req setup` and commit it"))
            if not is_installed(root):
                out.append(_check("warning", "merge_driver_missing",
                                  "reqtool's merge driver is not registered in this clone: run `req setup`"))

    # uncommitted generated files
    if is_git_repo(root):
        for path in dirty_paths(root, ("exports", "docs-dist", "dist")):
            out.append(_check("warning", "uncommitted_generated", f"Generated file not committed: {path}"))

    errors = sum(1 for c in out if c["level"] == "error")
    return {"ok": errors == 0, "errors": errors, "warnings": len(out) - errors, "checks": out}
