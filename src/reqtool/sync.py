"""
reqtool.sync
============
Sharing the requirements repository through a git remote (#348): fetch, pull, push and sync.

Credentials come from the user's own git setup (credential helper or SSH agent); reqtool never stores them.
Network commands never prompt and time out, so a missing credential is an error rather than a hang.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from .git_ops import has_conflicts, is_git_repo, remotes, run_git

NETWORK_TIMEOUT = 180
# Lines in git's output that mean the remote refused a push to a protected branch.
_PROTECTED_HINTS = ("protected branch", "GH006", "pre-receive hook declined", "not allowed to push")


class SyncError(RuntimeError):
    """A sync step failed; the message says what to do next."""

    def __init__(self, message: str, code: str = "sync_failed") -> None:
        super().__init__(message)
        self.code = code


def _network(args: list[str], root: Path) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        res = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8",
                             errors="replace", env=env, timeout=NETWORK_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise SyncError(f"git {args[0]} timed out after {NETWORK_TIMEOUT}s", "timeout")
    if res.returncode != 0:
        raise SyncError(f"git {args[0]} failed: {(res.stderr or res.stdout).strip()[:500]}", "git_error")
    return (res.stdout + res.stderr).strip()


def _out(args: list[str], root: Path) -> Optional[str]:
    rc, out, _ = run_git(args, root)
    return out.strip() if rc == 0 else None


def status(root: Path) -> dict[str, Any]:
    """Branch, upstream and how far ahead of and behind it the branch is (as of the last fetch)."""
    branch = _out(["rev-parse", "--abbrev-ref", "HEAD"], root) or ""
    upstream = _out(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root) or ""
    ahead = behind = 0
    if upstream:
        counts = (_out(["rev-list", "--left-right", "--count", "@{u}...HEAD"], root) or "0 0").split()
        behind, ahead = int(counts[0]), int(counts[1])
    return {"branch": branch, "upstream": upstream, "ahead": ahead, "behind": behind, "remotes": remotes(root)}


def _require_remote(root: Path) -> None:
    if not is_git_repo(root):
        raise SyncError("The repository is not under git", "not_git_repo")
    if not remotes(root):
        raise SyncError("No git remote is configured: run `git remote add origin <url>`", "no_remote")
    if has_conflicts(root):
        raise SyncError("Resolve the merge in progress first", "conflict")


def fetch(root: Path) -> dict[str, Any]:
    _require_remote(root)
    _network(["fetch", "--prune", "--all"], root)
    return status(root)


def pull(root: Path, strategy: str = "rebase") -> dict[str, Any]:
    """Bring in the upstream's commits. Local commits are rebased (or merged) and local edits kept.

    On a conflict the repository is left in git's merge or rebase state, so the usual tools resolve it and
    reqtool refuses writes until then.
    """
    _require_remote(root)
    before = _out(["rev-parse", "HEAD"], root)
    if not status(root)["upstream"]:
        raise SyncError("This branch has no upstream yet: push it first", "no_upstream")
    args = ["pull", "--rebase" if strategy == "rebase" else "--no-rebase", "--autostash"]
    try:
        _network(args, root)
    except SyncError as exc:
        if has_conflicts(root):
            raise SyncError("The pull stopped on a conflict: resolve it with git, then sync again", "conflict") from exc
        raise
    after = _out(["rev-parse", "HEAD"], root)
    changed: list[str] = []
    if before and after and before != after:
        changed = (_out(["diff", "--name-only", before, after], root) or "").splitlines()
    return {**status(root), "changed": changed}


def push(root: Path) -> dict[str, Any]:
    """Push the current branch, setting its upstream on the first push."""
    _require_remote(root)
    state = status(root)
    if state["branch"] == "HEAD":
        raise SyncError("Not on a branch (detached HEAD)", "detached")
    args = ["push"] if state["upstream"] else ["push", "-u", state["remotes"][0], state["branch"]]
    try:
        _network(args, root)
    except SyncError as exc:
        text = str(exc)
        if any(h in text for h in _PROTECTED_HINTS):
            raise SyncError(f"The remote does not accept pushes to {state['branch']}: start a change set and "
                            "open a pull request for it instead", "protected_branch") from exc
        if "non-fast-forward" in text or "fetch first" in text or "[rejected]" in text:
            raise SyncError("The remote has commits you do not have yet: sync again", "behind") from exc
        raise
    return status(root)


def sync(root: Path, strategy: str = "rebase", after_pull: Optional[Callable[[], dict[str, Any]]] = None,
         push_changes: bool = True, attempts: int = 3) -> dict[str, Any]:
    """Fetch, pull, run ``after_pull`` (reload, finalise, validate), then push.

    A branch with no upstream yet is pushed without a pull. ``after_pull`` may return ``_undo``, a callable that
    takes back a commit it made (finalised IDs): when another clone pushed in the meantime, that commit is undone
    and the whole round is tried again on top of the new remote, so two clones never pick the same number.
    """
    _require_remote(root)
    changed: list[str] = []
    for attempt in range(attempts):
        fetch(root)
        pulled = pull(root, strategy) if status(root)["upstream"] else {"changed": []}
        changed += [p for p in pulled["changed"] if p not in changed]
        extra = after_pull() if after_pull else {}
        undo = extra.pop("_undo", None)
        pushed = push_changes and (status(root)["ahead"] > 0 or not status(root)["upstream"])
        if not pushed:
            break
        try:
            push(root)
            break
        except SyncError as exc:
            if exc.code != "behind" or attempt == attempts - 1:
                raise
            if undo:
                undo()
    return {**status(root), "changed": changed, "pushed": pushed, **extra}


# Errors a merge of independently made changes can cause, as opposed to an item's own gaps.
MERGE_CODES = frozenset({
    "duplicate_id", "hash_mismatch", "missing_hash", "broken_uid_ref", "deleted_parent_ref", "parent_cycle",
    "hierarchy_violation", "relationship_violation", "approval_signature_invalid", "lock_hash_mismatch",
    "lock_module_missing",
})


def _error_keys(store: Any) -> set[tuple]:
    from .validation import validate_all
    return {(e.get("code"), e.get("uid"), e.get("field"), e.get("message")) for e in validate_all(store)["errors"]}


def finalise_ids(store: Any) -> dict[str, Any]:
    """Finalise provisional IDs (#349) of committed items and commit the renames as the current user.

    Items with uncommitted edits are left for the next sync, so their edits are not swept into this commit.
    Returns the renames and an ``_undo`` that drops the commit again.
    """
    from .git_ops import attribution, commit, dirty_paths, stage_file
    from .identity import MissingIdentity, with_trailers
    from .ids import finalise
    dirty = {Path(p).stem for p in dirty_paths(store.root, ("requirements",))}
    renamed = finalise(store, exclude=dirty)
    if not renamed:
        return {"finalised": []}
    paths = [store.req_path(r["uid"]) for r in renamed]
    try:
        who = attribution(store, paths)
    except MissingIdentity as exc:
        raise SyncError(str(exc), "no_git_identity")
    for p in paths:
        stage_file(store.root, p)
    message = "Finalise provisional IDs\n\n" + "\n".join(f"{r['old']} -> {r['new']}" for r in renamed)
    sha = commit(store.root, with_trailers(message, who.trailers), who.author.name, who.author.email, paths=paths,
                 committer_name=who.committer.name, committer_email=who.committer.email,
                 sign=store.config.git.sign_commits)

    def undo() -> None:
        if _out(["rev-parse", "HEAD"], store.root) == sha:
            run_git(["reset", "--keep", "HEAD~1"], store.root)
    return {"finalised": renamed, "_undo": undo}


def refresh(store: Any, known: set[tuple]) -> dict[str, Any]:
    """After a pull: reload every file, finalise provisional IDs when on the default branch, and report the
    merge problems (``MERGE_CODES``) the pull brought in.

    ``known`` are the errors found before the pull, so problems the repository already had are not repeated.
    """
    from .ids import strategy
    from .validation import validate_all
    store.load()
    extra: dict[str, Any] = {"finalised": []}
    if strategy(store.config) == "provisional" and status(store.root)["branch"] == store.config.git.default_branch:
        extra = finalise_ids(store)
    report = validate_all(store)
    new = [e for e in report["errors"] if e.get("code") in MERGE_CODES
           and (e.get("code"), e.get("uid"), e.get("field"), e.get("message")) not in known]
    return {**extra,
            "validation": {"merge_errors": new, "errors": len(report["errors"]), "warnings": len(report["warnings"])}}


def as_local_user(fn: Callable[[], Any], root: Path) -> Any:
    """Run ``fn`` with the git user as the default author of history entries (as a local-mode request has)."""
    from .actor import local_author
    from .identity import git_identity
    me = git_identity(root)
    token = local_author.set(me.name if me else None)
    try:
        return fn()
    finally:
        local_author.reset(token)


def sync_store(store: Any, push_changes: bool = True) -> dict[str, Any]:
    from .merge import driver_command, install
    _require_remote(store.root)
    # The merge driver lives in each clone's own git config, so register it before pulling (#350).
    installed = install(store.root, driver_command(), attributes=False)
    known = _error_keys(store)
    result = as_local_user(
        lambda: sync(store.root, store.config.git.pull_strategy, lambda: refresh(store, known), push_changes),
        store.root)
    return {**result, "merge_driver_installed": installed}


def pull_store(store: Any) -> dict[str, Any]:
    known = _error_keys(store)
    result = {**pull(store.root, store.config.git.pull_strategy), **refresh(store, known)}
    result.pop("_undo", None)
    return result
