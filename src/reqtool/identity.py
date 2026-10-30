"""
reqtool.identity
================
Who a commit is attributed to (#347). The git author is always the person who made the change.

Without a logged-in user (local and shared-repo modes) the author and committer are the user's own git
identity, exactly as if they had run ``git commit`` themselves. With a logged-in user (server mode) the
author is the user who edited the item since its last commit, the committer is the server's identity
(``git.commit_name`` / ``git.commit_email``), other editors become ``Co-authored-by`` trailers and a
different person pressing commit is recorded as ``Committed-by``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .fileio import yaml_loads_safe
from .git_ops import run_git


class MissingIdentity(RuntimeError):
    """No git identity is configured, so a commit cannot say who made it."""


NO_IDENTITY = ("No git identity is configured: run `git config --global user.name \"Your Name\"` and "
               "`git config --global user.email you@example.com`")


@dataclass(frozen=True)
class Identity:
    name: str
    email: str

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


@dataclass
class Attribution:
    author: Identity
    committer: Identity
    trailers: list[str] = field(default_factory=list)


def git_identity(root: Path) -> Optional[Identity]:
    """The git identity in effect for ``root`` (repository, global or system config), or None."""
    rc_n, name, _ = run_git(["config", "user.name"], root)
    rc_e, email, _ = run_git(["config", "user.email"], root)
    if rc_n == 0 and rc_e == 0 and name.strip() and email.strip():
        return Identity(name.strip(), email.strip())
    return None


def tool_identity(config: Any) -> Identity:
    return Identity(config.git.commit_name, config.git.commit_email)


def entries_since(older: list[dict[str, Any]], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The entries of ``history`` added after ``older`` (an earlier copy of it).

    Matches the newest entry of ``older`` rather than counting, because history is trimmed to
    ``max_history_entries``. Nothing is new when that entry is no longer there.
    """
    if not older:
        return history
    last = older[-1]
    key = (last.get("version"), last.get("date"), last.get("summary"))
    at = next((i for i in range(len(history) - 1, -1, -1)
               if (history[i].get("version"), history[i].get("date"), history[i].get("summary")) == key), None)
    return history[at + 1:] if at is not None else []


def committed_copy(root: Path, path: Path, ref: str = "HEAD") -> Optional[dict[str, Any]]:
    """``path`` as it is in ``ref``, or None when it is not there."""
    rc, text, _ = run_git(["show", f"{ref}:{path.relative_to(root).as_posix()}"], root)
    data = yaml_loads_safe(text) if rc == 0 else None
    return data if isinstance(data, dict) else None


def uncommitted_editors(root: Path, path: Path, history: list[dict[str, Any]]) -> list[str]:
    """Who changed the item since it was last committed, least recent first."""
    committed = (committed_copy(root, path) or {}).get("history") or []
    names: list[str] = []
    for entry in entries_since(committed, history):
        name = entry.get("modified_by")
        if name:
            if name in names:
                names.remove(name)
            names.append(name)
    return names


def user_identity(root: Path, config: Any, username: str) -> Optional[Identity]:
    """A server account as a git identity. Without an email the committer's domain is used."""
    from .auth import UserStore
    user = UserStore(root).load_users().get(username)
    if user is None:
        return None
    domain = config.git.commit_email.rpartition("@")[2] or "localhost"
    return Identity(user.get("full_name") or username, user.get("email") or f"{username}@{domain}")


def attribution(root: Path, config: Any, editors: list[str], actor: Optional[str]) -> Attribution:
    """Author, committer and trailers for a commit of changes made by ``editors``, requested by ``actor``."""
    if actor is None:
        me = git_identity(root)
        if me is None:
            raise MissingIdentity(NO_IDENTITY)
        return Attribution(me, me)
    people = [p for p in (user_identity(root, config, n) for n in editors) if p is not None]
    clicker = user_identity(root, config, actor) or Identity(actor, f"{actor}@localhost")
    author = people[-1] if people else clicker
    trailers = [f"Co-authored-by: {p}" for p in people[:-1] if p != author]
    if clicker != author:
        trailers.append(f"Committed-by: {clicker}")
    return Attribution(author, tool_identity(config), trailers)


def for_commit(store: Any, paths: list[Path]) -> Attribution:
    """Attribution for committing ``paths`` as they are on disk now, requested by the current user."""
    from .actor import current_actor
    editors: list[str] = []
    for path in paths:
        data = store.storage.read(path) if store.storage.exists(path) else {}
        for name in uncommitted_editors(store.root, path, (data or {}).get("history") or []):
            if name in editors:
                editors.remove(name)
            editors.append(name)
    return attribution(store.root, store.config, editors, current_actor.get())


def with_trailers(message: str, trailers: list[str]) -> str:
    return message + ("\n\n" + "\n".join(trailers) if trailers else "")


def git_env(who: Attribution, committer: Optional[Identity] = None) -> dict[str, str]:
    """Environment that makes git record ``who`` (a tag's tagger is the committer)."""
    c = committer or who.committer
    return {"GIT_AUTHOR_NAME": who.author.name, "GIT_AUTHOR_EMAIL": who.author.email,
            "GIT_COMMITTER_NAME": c.name, "GIT_COMMITTER_EMAIL": c.email}


def for_action(store: Any) -> Attribution:
    """Attribution for a git action with no item edits of its own (a baseline tag, a merge)."""
    from .actor import current_actor
    return attribution(store.root, store.config, [], current_actor.get())
