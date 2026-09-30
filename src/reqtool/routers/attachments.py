"""
reqtool.routers.attachments
===========================
FastAPI router for attachment upload, download, and listing endpoints.
"""

from __future__ import annotations

import logging
import re
import mimetypes
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from reqtool.store import Store
from reqtool.stores.attachment_store import _sanitize_filename
from .deps import get_store, not_found, fire_webhook

log = logging.getLogger(__name__)

router = APIRouter(tags=["attachments"])


@router.get("/artefacts/{uid}/attachments")
def list_artefact_attachments(uid: str, store: Store = Depends(get_store)):
    return store.list_attachments(uid)


@router.post("/artefacts/{uid}/attachments", status_code=201)
async def upload_artefact_attachment(uid: str, request: Request, author: str = "reqtool", store: Store = Depends(get_store)):
    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail={"error": "empty", "message": "No file data"})
    if store._get_artefact(uid) is None:
        raise not_found(uid)
    content_disposition = request.headers.get("content-disposition", "")
    filename = "attachment"
    if "filename=" in content_disposition:
        filename = content_disposition.split("filename=")[-1].strip('"').strip()
    description = request.headers.get("x-description", "")
    filename = re.sub(r'[^\w\-_\. ]', '_', filename)[:200]
    record = store.add_attachment(uid, filename, data, author=author, description=description)
    fire_webhook(store, "attachment_added", {"uid": uid, "filename": filename})
    return record


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
def list_attachments(uid: str, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    return req.get("attachments", [])


@router.post("/requirements/{uid}/attachments", status_code=201)
async def upload_attachment(uid: str, request: Request, author: str = "reqtool", store: Store = Depends(get_store)):
    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail={"error": "empty", "message": "No file data received"})
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    content_disposition = request.headers.get("content-disposition", "")
    filename = "attachment"
    if "filename=" in content_disposition:
        filename = content_disposition.split("filename=")[-1].strip('"').strip()
    description = request.headers.get("x-description", "")
    filename = re.sub(r'[^\w\-_\. ]', '_', filename)[:200]
    record = store.add_attachment(uid, filename, data, author=author, description=description)
    fire_webhook(store, "attachment_added", {"uid": uid, "filename": filename})
    return record


@router.get("/requirements/{uid}/attachments/{filename}")
def download_attachment(uid: str, filename: str, store: Store = Depends(get_store)):
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
def delete_attachment(uid: str, filename: str, store: Store = Depends(get_store)):
    ok = store.delete_attachment(uid, filename)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
    return {"deleted": filename}
