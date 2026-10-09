"""
reqtool.features.changesets
===========================
Group edits on a git branch, review the requirement and field-level diff, then merge (FEAT-02).
"""

from __future__ import annotations

import re
from typing import Any

from reqtool.git_ops import run_git, dirty_paths, ensure_git_config, is_git_repo
from .diff import ref_diff

PREFIX = "changeset/"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$")
TRACKED = ("requirements", "principles", "decisions", "modules", "products")


class ChangeSetError(ValueError):
    pass


def _git(store, *args: str) -> str:
    code, out, err = run_git(list(args), store.root)
    if code != 0:
        raise ChangeSetError((err or out).strip() or f"git {args[0]} failed")
    return out.strip()


def _branch(name: str) -> str:
    if not NAME.match(name or "") or ".." in name:
        raise ChangeSetError("Change set names use letters, digits, '.', '_' and '-'")
    return PREFIX + name


def current_branch(store) -> str:
    return _git(store, "rev-parse", "--abbrev-ref", "HEAD")


def _base_of(store, branch: str) -> str:
    code, out, _ = run_git(["config", f"branch.{branch}.reqtool-base"], store.root)
    return out.strip() if code == 0 and out.strip() else "main"


def create(store, name: str) -> dict[str, Any]:
    """Start a change set from the current branch and switch to it."""
    if not is_git_repo(store.root):
        raise ChangeSetError("The repository is not under git")
    branch = _branch(name)
    base = current_branch(store)
    if base.startswith(PREFIX):
        raise ChangeSetError("Already on a change set: merge or leave it first")
    if dirty_paths(store.root, TRACKED):
        raise ChangeSetError("Commit or discard your changes before starting a change set")
    _git(store, "checkout", "-b", branch)
    _git(store, "config", f"branch.{branch}.reqtool-base", base)
    store.load()
    return {"name": name, "branch": branch, "base": base}


def listing(store) -> list[dict[str, Any]]:
    if not is_git_repo(store.root):
        return []
    here = current_branch(store)
    out = _git(store, "branch", "--list", PREFIX + "*", "--format=%(refname:short)")
    return [{"name": b[len(PREFIX):], "branch": b, "base": _base_of(store, b), "current": b == here}
            for b in out.splitlines() if b]


def diff(store, name: str) -> dict[str, Any]:
    branch = _branch(name)
    base = _base_of(store, branch)
    try:
        return {"name": name, "base": base, **ref_diff(store.root, base, branch)}
    except ValueError as exc:
        raise ChangeSetError(str(exc))


def switch(store, target: str) -> dict[str, Any]:
    """Leave the change set (``target`` is the base branch name) or enter another one."""
    if dirty_paths(store.root, TRACKED):
        raise ChangeSetError("Commit or discard your changes before switching")
    branches = _branches(store)
    dest = target if target in branches else _branch(target)
    if dest not in branches:
        raise ChangeSetError(f"No branch or change set named '{target}'")
    _git(store, "checkout", dest)
    store.load()
    return {"branch": current_branch(store)}


def _branches(store) -> set[str]:
    return set(_git(store, "branch", "--format=%(refname:short)").splitlines())


def merge(store, name: str, reviewed_by: str) -> dict[str, Any]:
    """Merge a change set into its base. A named reviewer is required (the review step)."""
    if not (reviewed_by or "").strip():
        raise ChangeSetError("reviewed_by is required: a change set is merged only after review")
    branch = _branch(name)
    base = _base_of(store, branch)
    if dirty_paths(store.root, TRACKED):
        raise ChangeSetError("Commit or discard your changes before merging")
    ensure_git_config(store.root, store.config.git.commit_name, store.config.git.commit_email)
    _git(store, "checkout", base)
    code, out, err = run_git(["merge", "--no-ff", branch, "-m", f"Merge change set {name} (reviewed by {reviewed_by.strip()})"], store.root)
    if code != 0:
        run_git(["merge", "--abort"], store.root)
        _git(store, "checkout", branch)
        store.load()
        raise ChangeSetError("Merge conflict: " + (err or out).strip()[:300])
    store.load()
    return {"merged": name, "into": base, "reviewed_by": reviewed_by.strip(), "sha": _git(store, "rev-parse", "--short", "HEAD")}
