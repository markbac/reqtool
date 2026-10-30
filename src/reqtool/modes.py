"""
reqtool.modes
=============
How a repository is used (#346).

``local``
    One person, one repository, no login.
``server``
    A central ``reqtool-server`` with logins and roles, used by many clients.
``shared-repo``
    Each person runs reqtool locally against their own clone and shares work by pushing to and pulling
    from a git remote. The git host and CI act as the gatekeeper.

The repository's default is ``mode`` in ``.reqtool/config.yaml``. ``REQTOOL_MODE`` overrides it on one
machine, so a server can host a checkout of a repository whose default is ``shared-repo``.
"""

from __future__ import annotations

import os
from typing import Optional

MODES = ("local", "server", "shared-repo")


def resolve_mode(configured: Optional[str] = None, explicit: Optional[str] = None) -> str:
    mode = (explicit or os.environ.get("REQTOOL_MODE") or configured or "local").strip().lower()
    if mode not in MODES:
        raise ValueError(f"Invalid operating mode '{mode}' (expected one of {MODES})")
    return mode


def default_auth(mode: str) -> str:
    """The authentication mode an operating mode runs with unless one is given."""
    return "required" if mode == "server" else "local"
