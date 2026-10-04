"""
reqtool.routers.attachments
===========================
FastAPI router for attachment upload, download, and listing endpoints.
"""

from __future__ import annotations

import logging
import os
import re
import mimetypes
from email.message import Message
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from reqtool.store import Store
from reqtool.stores.attachment_store import _sanitize_filename
from .deps import get_store, not_found, publish_event, ReqUid

log = logging.getLogger(__name__)

router = APIRouter(tags=["attachments"])

MAX_ATTACHMENTS_PER_ARTEFACT = 100


def max_upload_bytes() -> int:
    """Upload size limit; ``REQTOOL_MAX_UPLOAD_MB`` (default 25)."""
    try:
        return int(float(os.environ.get("REQTOOL_MAX_UPLOAD_MB", "25")) * 1024 * 1024)
    except ValueError:
        return 25 * 1024 * 1024


def _too_large(limit: int) -> HTTPException:
    return HTTPException(status_code=413, detail={
        "error": "too_large", "message": f"Upload exceeds the {limit // (1024 * 1024) or limit} MB limit"})


async def _read_limited(request: Request) -> bytes:
    """Read the body without ever holding more than the limit (plus one chunk)."""
    limit = max_upload_bytes()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _too_large(limit)
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise _too_large(limit)
        chunks.append(chunk)
    return b"".join(chunks)


def _upload_filename(request: Request) -> str:
    """Filename from Content-Disposition, parsed as a header, then reduced to safe characters."""
    msg = Message()
    msg["content-disposition"] = request.headers.get("content-disposition", "")
    name = msg.get_filename() or "attachment"
    return re.sub(r"[^\w\-_\. ]", "_", os.path.basename(name.replace("\\", "/")))[:200] or "attachment"


def _store_upload(store: Store, uid: str, filename: str, data: bytes, author: str, description: str):
    existing = {a.get("filename") for a in store.list_attachments(uid) or []}
    if filename not in existing and len(existing) >= MAX_ATTACHMENTS_PER_ARTEFACT:
        raise HTTPException(status_code=409, detail={
            "error": "too_many", "message": f"At most {MAX_ATTACHMENTS_PER_ARTEFACT} attachments per item"})
    record = store.add_attachment(uid, filename, data, author=author, description=description)
    publish_event(store, "attachment_added", {"uid": uid, "filename": filename})
    return record


@router.get("/artefacts/{uid}/attachments")
def list_artefact_attachments(uid: str, store: Store = Depends(get_store)):
    return store.list_attachments(uid)


@router.post("/artefacts/{uid}/attachments", status_code=201)
async def upload_artefact_attachment(uid: str, request: Request, author: str = "reqtool", store: Store = Depends(get_store)):
    if not store.has_artefact(uid):
        raise not_found(uid)
    data = await _read_limited(request)
    if not data:
        raise HTTPException(status_code=422, detail={"error": "empty", "message": "No file data"})
    return _store_upload(store, uid, _upload_filename(request), data, author, request.headers.get("x-description", ""))


@router.get("/artefacts/{uid}/attachments/{filename}")
def download_artefact_attachment(uid: str, filename: str, store: Store = Depends(get_store)):
    try:
        clean_name = _sanitize_filename(filename)
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
    target_dir = store.attachment_dir(uid).resolve()
    path = (target_dir / clean_name).resolve()
    if not path.is_relative_to(target_dir) or not path.exists():
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
    mime, _ = mimetypes.guess_type(clean_name)
    return Response(
        content=path.read_bytes(),
        media_type=mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{clean_name}"'},
    )


@router.delete("/artefacts/{uid}/attachments/{filename}")
def delete_artefact_attachment(uid: str, filename: str, store: Store = Depends(get_store)):
    ok = store.delete_attachment(uid, filename)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
    return {"deleted": filename}


@router.get("/requirements/{uid}/attachments")
def list_attachments(uid: ReqUid, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    return req.get("attachments", [])


@router.post("/requirements/{uid}/attachments", status_code=201)
async def upload_attachment(uid: ReqUid, request: Request, author: str = "reqtool", store: Store = Depends(get_store)):
    if store.get_requirement(uid) is None:
        raise not_found(uid)
    data = await _read_limited(request)
    if not data:
        raise HTTPException(status_code=422, detail={"error": "empty", "message": "No file data received"})
    return _store_upload(store, uid, _upload_filename(request), data, author, request.headers.get("x-description", ""))


@router.get("/requirements/{uid}/attachments/{filename}")
def download_attachment(uid: ReqUid, filename: str, store: Store = Depends(get_store)):
    try:
        clean_name = _sanitize_filename(filename)
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
    target_dir = store.attachment_dir(uid).resolve()
    path = (target_dir / clean_name).resolve()
    if not path.is_relative_to(target_dir) or not path.exists():
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
    mime, _ = mimetypes.guess_type(clean_name)
    mime = mime or "application/octet-stream"
    return Response(
        content=path.read_bytes(),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{clean_name}"'},
    )


@router.delete("/requirements/{uid}/attachments/{filename}")
def delete_attachment(uid: ReqUid, filename: str, store: Store = Depends(get_store)):
    ok = store.delete_attachment(uid, filename)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
    return {"deleted": filename}
