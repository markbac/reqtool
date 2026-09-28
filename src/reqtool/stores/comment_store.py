"""
reqtool.stores.comment_store
============================
Comment storage helper functions for managing discussion comments on requirements, principles, and TBDs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from reqtool.fileio import load_yaml, save_yaml, utcnow_iso, uuid7

log = logging.getLogger(__name__)


def comments_path(repo_root: Path, uid: str) -> Path:
    return repo_root / "comments" / f"{uid}.yaml"


def get_comments(repo_root: Path, uid: str) -> list[dict[str, Any]]:
    path = comments_path(repo_root, uid)
    if not path.exists():
        return []
    data = load_yaml(path)
    return data if isinstance(data, list) else []


def add_comment(
    repo_root: Path,
    uid: str,
    text: str,
    author: str,
    reply_to: Optional[str] = None,
) -> dict[str, Any]:
    (repo_root / "comments").mkdir(exist_ok=True)
    comments = get_comments(repo_root, uid)
    comment = {
        "uid": uuid7(),
        "text": text,
        "author": author,
        "created_at": utcnow_iso(),
        "updated_at": None,
        "reply_to": reply_to,
        "resolved": False,
    }
    comments.append(comment)
    save_yaml(comments_path(repo_root, uid), comments)
    return comment


def update_comment(
    repo_root: Path,
    uid: str,
    comment_uid: str,
    text: str,
) -> Optional[dict[str, Any]]:
    comments = get_comments(repo_root, uid)
    for c in comments:
        if c.get("uid") == comment_uid:
            c["text"] = text
            c["updated_at"] = utcnow_iso()
            save_yaml(comments_path(repo_root, uid), comments)
            return c
    return None


def resolve_comment(
    repo_root: Path,
    uid: str,
    comment_uid: str,
    resolved: bool = True,
) -> Optional[dict[str, Any]]:
    comments = get_comments(repo_root, uid)
    for c in comments:
        if c.get("uid") == comment_uid:
            c["resolved"] = resolved
            save_yaml(comments_path(repo_root, uid), comments)
            return c
    return None


def delete_comment(repo_root: Path, uid: str, comment_uid: str) -> bool:
    comments = get_comments(repo_root, uid)
    new = [c for c in comments if c.get("uid") != comment_uid]
    if len(new) == len(comments):
        return False
    save_yaml(comments_path(repo_root, uid), new)
    return True
