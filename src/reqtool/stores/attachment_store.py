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
    dest_dir = attachment_dir(store.root, uid)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

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
    dest = attachment_dir(store.root, uid) / filename
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
