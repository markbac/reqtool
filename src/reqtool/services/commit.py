"""Committing one artefact: bump its version, commit only its file, and undo the bump if git fails (ARC-16)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from reqtool import git_ops
from reqtool.identity import MissingIdentity, with_trailers
from .errors import GitFailure, Invalid, MergeConflicts, NoGitIdentity


def commit_message(message: str | None) -> str:
    """The commit message, or a 422 before anything is changed (git would reject an empty one)."""
    text = (message or "").strip()
    if not text:
        raise Invalid("A commit message is required")
    return text


def commit_artefact(store: Any, message: str | None, path: Path, *, bump: Callable[[str], Any],
                    undo: Callable[[], Any], version: Callable[[], str], git: Any = git_ops) -> dict[str, Any]:
    """``bump(message)`` records the version and history entry, ``undo()`` reverses it and ``version()`` reads the
    new version. Nothing is written after the commit, so the working tree stays clean and the SHA lives in git."""
    if git.has_conflicts(store.root):
        raise MergeConflicts()
    text = commit_message(message)
    try:
        who = git.attribution(store, [path])  # before the bump, which adds a history entry of its own
    except MissingIdentity as exc:
        raise NoGitIdentity(str(exc))
    try:
        bump(text)
        git.stage_file(store.root, path)
        sha = git.commit(store.root, with_trailers(text, who.trailers), who.author.name, who.author.email,
                         paths=[path], committer_name=who.committer.name, committer_email=who.committer.email,
                         sign=store.config.git.sign_commits)
        return {"commit_sha": sha, "version": version()}
    except RuntimeError as exc:
        undo()
        git.unstage_file(store.root, path)
        raise GitFailure(str(exc))
