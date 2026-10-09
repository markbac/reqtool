"""Who may do what (roles). One table drives the server's checks and the buttons the UI shows.

Three roles:

``viewer``  reads everything and changes nothing.
``editor``  adds and changes data: items, comments, attachments, links, imports, iterations, commits.
``admin``   also does the advanced work: deleting, workflows, configuration, modules and baselines,
            repository creation and switching, webhooks, writing-check settings and users.

Roles are enforced in ``--auth required`` mode, where each caller has a login. In ``local`` mode there is
a single unnamed user on this machine, who is treated as an administrator.
"""

from __future__ import annotations

import re
from typing import Optional

ROLES = ("viewer", "editor", "admin")
_RANK = {role: rank for rank, role in enumerate(ROLES)}

# Action name -> lowest role that may do it. The UI asks for these names; the server's rules below use them too.
ACTIONS: dict[str, str] = {
    "read": "viewer",
    "write": "editor",             # create and change items, comments, attachments, links, imports
    "delete": "admin",             # delete or restore items
    "manage_workflow": "admin",    # states, transitions, guards, which workflow a type uses
    "manage_lint": "admin",        # writing-check and Vale settings
    "manage_config": "admin",      # repository configuration, enums, custom fields, templates, automation rules
    "manage_repo": "admin",        # create or switch the repository, change sets
    "manage_modules": "admin",     # modules, products, baselines
    "manage_webhooks": "admin",
    "manage_users": "admin",
}

# (method or None for any, path pattern, action). A request needing an action needs that action's role.
_RULES: tuple[tuple[Optional[str], str, str], ...] = (
    (None, r"/repo/.*", "manage_repo"),
    ("POST", r"/changesets(/.*)?", "manage_repo"),
    ("PUT", r"/config", "manage_config"),
    ("PUT", r"/enums/repo", "manage_config"),
    ("PUT", r"/custom-fields", "manage_config"),
    ("PUT", r"/templates", "manage_config"),
    ("PUT", r"/automation/rules", "manage_config"),
    ("PUT", r"/workflow", "manage_workflow"),
    ("POST", r"/workflows(/.*)?", "manage_workflow"),
    ("PUT", r"/workflows/.*", "manage_workflow"),
    ("DELETE", r"/workflows/.*", "manage_workflow"),
    ("PUT", r"/hierarchy/.*", "manage_workflow"),
    ("PUT", r"/lint/config", "manage_lint"),
    ("POST", r"/webhooks", "manage_webhooks"),
    ("DELETE", r"/webhooks(/.*)?", "manage_webhooks"),
    ("POST", r"/auth/users", "manage_users"),
    ("POST", r"/baselines", "manage_modules"),
    ("POST", r"/modules(/.*)?", "manage_modules"),
    ("POST", r"/products(/.*)?", "manage_modules"),
    ("DELETE", r"/(requirements|principles|decisions|tbds|iterations)/[^/]+", "delete"),
)
_COMPILED = tuple((m, re.compile(p), a) for m, p, a in _RULES)


# POST endpoints that only compute a result and change nothing, so a read-only user may call them.
_READ_ONLY_POSTS = frozenset({"/lint/text"})


def changes_data(method: str, path: str) -> bool:
    """False for requests a viewer may make: reads, and the few POSTs that only compute."""
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    return not (method == "POST" and (path.rstrip("/") or "/") in _READ_ONLY_POSTS)


def role_rank(role: Optional[str]) -> int:
    return _RANK.get(role or "", -1)


def required_action(method: str, path: str) -> Optional[str]:
    """The action a request needs beyond ``write``/``read``, or None when any editor may make it."""
    for rule_method, pattern, action in _COMPILED:
        if (rule_method is None or rule_method == method) and pattern.fullmatch(path.rstrip("/") or "/"):
            return action
    return None


def can(role: Optional[str], action: str) -> bool:
    needed = ACTIONS.get(action)
    return needed is not None and role_rank(role) >= role_rank(needed)


def permissions_for(role: Optional[str]) -> list[str]:
    return [action for action in ACTIONS if can(role, action)]
