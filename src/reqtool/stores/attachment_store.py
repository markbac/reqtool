"""
reqtool.stores.attachment_store
===============================
Attachment storage helper functions for saving, deleting, and listing file attachments.
"""

from __future__ import annotations

import logging
import hashlib
from pathlib import Path
from typing import Any, Optional

from reqtool.fileio import utcnow_iso

log = logging.getLogger(__name__)


import os
import re

def _sanitize_filename(filename: str) -> str:
    """Sanitize filename and strip path traversal characters."""
    clean = os.path.basename(filename).strip()
    clean = re.sub(r'[^\w\-_\. ]', '_', clean)[:200]
    if not clean or clean in (".", ".."):
        raise ValueError("Invalid attachment filename")
    return clean


def attachment_dir(repo_root: Path, uid: str) -> Path:
    return repo_root / "attachments" / uid


def add_attachment(
    store: Any,
    uid: str,
    filename: str,
    data: bytes,
    author: str = "reqtool",
    description: str = "",
) -> dict[str, Any]:
    filename = _sanitize_filename(filename)
    dest_dir = attachment_dir(store.root, uid)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = (dest_dir / filename).resolve()
    if not dest.is_relative_to(dest_dir.resolve()):
        raise ValueError("Path traversal attempt detected")

    sha256 = f"sha256:{hashlib.sha256(data).hexdigest()}"
    now = utcnow_iso()
    record = {
        "filename": filename,
        "size_bytes": len(data),
        "sha256": sha256,
        "added_by": author,
        "added_at": now,
        "description": description,
    }

    result = store._get_artefact(uid)
    if result is None:
        raise ValueError(f"Artefact {uid} not found")
    artefact, _ = result
    attachments = list(artefact.get("attachments", []))
    attachments = [a for a in attachments if a.get("filename") != filename]
    attachments.append(record)

    store._update_artefact(uid, {"attachments": attachments}, summary=f"Added attachment: {filename}")
    dest.write_bytes(data)
    return record


def delete_attachment(store: Any, uid: str, filename: str) -> bool:
    try:
        filename = _sanitize_filename(filename)
    except ValueError:
        return False
    dest_dir = attachment_dir(store.root, uid)
    dest = (dest_dir / filename).resolve()
    if not dest.is_relative_to(dest_dir.resolve()):
        return False
    if dest.exists():
        dest.unlink()
    result = store._get_artefact(uid)
    if result is None:
        return False
    artefact, _ = result
    before = artefact.get("attachments", [])
    after = [a for a in before if a.get("filename") != filename]
    if len(after) == len(before) and not dest.exists():
        return False
    store._update_artefact(uid, {"attachments": after}, summary=f"Removed attachment: {filename}")
    return True


def list_attachments(store: Any, uid: str) -> list[dict[str, Any]]:
    result = store._get_artefact(uid)
    if result is None:
        return []
    artefact, _ = result
    return artefact.get("attachments", [])
