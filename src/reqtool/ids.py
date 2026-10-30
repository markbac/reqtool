"""
reqtool.ids
===========
Human IDs that never collide across clones (#349).

With the ``provisional`` strategy a new item gets an ID made from its UID, such as ``FR-~1A2B3C4D``. The ``~``
cannot appear in an ID a person types, so it never clashes with a final one. ``req sync`` on the default branch
(or ``req finalise-ids``) then gives each provisional item the next free sequential ID of the merged tree,
oldest first, and records the rename in its history. A provisional ID keeps resolving after it is finalised.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Optional

from .modes import resolve_mode

_PROVISIONAL = re.compile(r"^.+-~(?P<tail>[0-9A-F]{8})$")


def strategy(config: Any) -> str:
    """``provisional`` or ``sequential``: the configured strategy, else provisional in shared-repo mode."""
    if config.ids.strategy:
        return config.ids.strategy
    return "provisional" if resolve_mode(config.mode) == "shared-repo" else "sequential"


def provisional_id(prefix: str, uid: str) -> str:
    return f"{prefix}-~{uid.replace('-', '')[-8:].upper()}"


def is_provisional(rid: Any) -> bool:
    return isinstance(rid, str) and _PROVISIONAL.match(rid) is not None


def resolve_provisional(requirements: dict[str, dict[str, Any]], key: str) -> Optional[str]:
    """The UID a provisional ID was made from, even after the item got its final ID."""
    m = _PROVISIONAL.match(key)
    if not m:
        return None
    tail = m["tail"].lower()
    hits = [u for u, r in requirements.items() if u.replace("-", "").endswith(tail) and not r.get("deleted")]
    return hits[0] if len(hits) == 1 else None


def _rename(store: Any, uid: str, new_id: str, summary: str) -> dict[str, str]:
    req = store.requirement_map()[uid]
    old = req.get("id", "")
    acs = [{**ac, "id": new_id + ac["id"][len(old):]} if str(ac.get("id", "")).startswith(old + "__") else ac
           for ac in req.get("acceptance_criteria") or []]
    fields: dict[str, Any] = {"id": new_id}
    if acs != (req.get("acceptance_criteria") or []):
        fields["acceptance_criteria"] = acs
    store.update_requirement(uid, fields, summary=summary)
    return {"uid": uid, "old": old, "new": new_id}


def finalise(store: Any, exclude: frozenset[str] | set[str] = frozenset()) -> list[dict[str, str]]:
    """Give every live provisional item (except the UIDs in ``exclude``) its sequential ID, oldest first.
    Returns the renames."""
    renamed = []
    for uid in sorted(u for u, r in store.requirement_map().items()
                      if u not in exclude and not r.get("deleted") and is_provisional(r.get("id"))):
        new_id = store.next_id_for_type(store.requirement_map()[uid].get("req_type", "functional"))
        renamed.append(_rename(store, uid, new_id, f"ID finalised: {store.requirement_map()[uid]['id']} -> {new_id}"))
    return renamed


def fix_duplicates(store: Any) -> list[dict[str, str]]:
    """Renumber all but the oldest live item of each duplicated ID. Returns the renames."""
    by_id: dict[str, list[str]] = defaultdict(list)
    for uid, r in store.requirement_map().items():
        if not r.get("deleted") and r.get("id"):
            by_id[r["id"]].append(uid)
    renamed = []
    for rid, uids in sorted(by_id.items()):
        for uid in sorted(uids)[1:]:
            new_id = store.next_id_for_type(store.requirement_map()[uid].get("req_type", "functional"))
            renamed.append(_rename(store, uid, new_id, f"Duplicate ID {rid} renumbered to {new_id}"))
    return renamed
