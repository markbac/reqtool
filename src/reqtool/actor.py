"""
reqtool.actor
=============
Who is making the current request. The access-control middleware sets the authenticated
user here, and the store records it as the author of history entries, comments and
attachments, so attribution never depends on a client-supplied name.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

current_actor: ContextVar[Optional[str]] = ContextVar("reqtool_actor", default=None)
current_role: ContextVar[Optional[str]] = ContextVar("reqtool_role", default=None)


def resolve_author(author: str = "reqtool") -> str:
    """The authenticated user when there is one, else the caller-supplied name."""
    return current_actor.get() or author


def can_modify_owned(owner: Optional[str]) -> bool:
    """May the current user change something authored by ``owner``? (Unauthenticated local use may.)"""
    actor = current_actor.get()
    return actor is None or current_role.get() == "admin" or owner == actor
