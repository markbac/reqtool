"""Committing one artefact: bump its version, commit only its file, and undo the bump if git fails (ARC-16)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from reqtool import git_ops
from .errors import GitFailure, Invalid, MergeConflicts


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
        bump(text)
        git.stage_file(store.root, path)
        sha = git.commit(store.root, text, store.config.git.commit_name, store.config.git.commit_email, paths=[path])
        return {"commit_sha": sha, "version": version()}
    except RuntimeError as exc:
        undo()
        git.unstage_file(store.root, path)
        raise GitFailure(str(exc))
