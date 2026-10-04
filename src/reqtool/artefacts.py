"""
reqtool.artefacts
=================
The rules every stored artefact (requirement, principle, decision/TBD) follows when it is created,
changed or deleted: how the version moves, how the content hash is kept, and what the append-only
history records. One implementation, so the three kinds cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from .actor import resolve_author
from .fileio import (
    bump_version, compute_principle_hash, compute_requirement_hash, compute_tbd_hash, utcnow_iso,
)


@dataclass(frozen=True)
class ArtefactKind:
    """What differs between kinds: where they live in the store and which fields their hash covers."""
    name: str
    collection: str                      # attribute of Store that holds them
    hash_fn: Callable[[dict[str, Any]], str]


REQUIREMENT = ArtefactKind("requirement", "requirements", compute_requirement_hash)
PRINCIPLE = ArtefactKind("principle", "principles", compute_principle_hash)
DECISION = ArtefactKind("decision", "decisions", compute_tbd_hash)

# Nested blocks whose sub-fields a caller may send alone (for example just ``approval.approved_by``).
DEEP_MERGE_KEYS = frozenset({"content", "approval", "review", "verification", "implementation"})


def history_entry(version: str, author: str, summary: str, change_ref: Optional[str] = None,
                  now: Optional[str] = None) -> dict[str, Any]:
    """One audit record. The author is the logged-in user when there is one."""
    return {"version": version, "date": now or utcnow_iso(), "modified_by": resolve_author(author),
            "summary": summary, "commit_sha": None, "change_ref": change_ref}


def seal_new(kind: ArtefactKind, data: dict[str, Any], author: str) -> dict[str, Any]:
    """Stamp a freshly built artefact: first history entry, content hash, timestamps unchanged."""
    data["history"] = [history_entry("1.0.0", author, "Initial draft.", now=data.get("created"))]
    data["content_hash"] = kind.hash_fn(data)
    return data


def apply_fields(data: dict[str, Any], fields: Mapping[str, Any], deep_merge: bool = False) -> None:
    """Write ``fields`` onto ``data``. With ``deep_merge`` the nested blocks are merged, not replaced."""
    for key, value in fields.items():
        if deep_merge and key in DEEP_MERGE_KEYS and isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value


def record_change(kind: ArtefactKind, data: dict[str, Any], increment: str, author: str,
                  summary: str, change_ref: Optional[str] = None) -> bool:
    """After ``data`` was edited: rehash, bump the version if the content changed, stamp the time and
    append to the history (never truncated: it is the audit trail). Returns whether the content changed."""
    old_hash = data.get("content_hash", "")
    new_hash = kind.hash_fn(data)
    changed = new_hash != old_hash
    if changed:
        data["version"] = bump_version(data.get("version", "1.0.0"), increment)
        data["content_hash"] = new_hash
    now = utcnow_iso()
    data["last_modified"] = now
    data["history"] = list(data.get("history") or []) + [
        history_entry(data["version"], author, summary, change_ref, now=now)]
    return changed


def mark_deleted(data: dict[str, Any]) -> None:
    """Soft delete: the file stays (git history, restores) and the item drops out of every live view."""
    data["deleted"] = True
    data["last_modified"] = utcnow_iso()
