"""
reqtool.routers.comments
========================
FastAPI router for artefact and requirement comment endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from reqtool.actor import can_modify_owned
from reqtool.store import Store
from .deps import get_store, not_found, publish_event, ReqUid

log = logging.getLogger(__name__)

router = APIRouter(tags=["comments"])


def _text(body: Any) -> str:
    """The comment text from a request body, or a 422 (never a 500 for a wrong type)."""
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "text is required"})
    return text.strip()


def _author_of(store: Store, uid: str, comment_uid: str) -> Any:
    for c in store.get_comments(uid):
        if c.get("uid") == comment_uid:
            return c.get("author")
    raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})


def _require_owner(store: Store, uid: str, comment_uid: str) -> None:
    if not can_modify_owned(_author_of(store, uid, comment_uid)):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Only the author or an administrator can change this comment"})


@router.get("/artefacts/{uid}/comments")
def list_artefact_comments(uid: str, store: Store = Depends(get_store)):
    return store.get_comments(uid)


@router.post("/artefacts/{uid}/comments", status_code=201)
def add_artefact_comment(uid: str, body: dict[str, Any], store: Store = Depends(get_store)):
    if store._get_artefact(uid) is None:
        raise not_found(uid)
    text = _text(body)
    author = body.get("author") if isinstance(body.get("author"), str) else "anonymous"
    reply_to = body.get("reply_to")
    comment = store.add_comment(uid, text, author, reply_to=reply_to)
    publish_event(store, "comment_added", {"uid": uid, "comment_uid": comment["uid"], "author": comment["author"]})
    return comment


@router.put("/artefacts/{uid}/comments/{comment_uid}")
def update_artefact_comment(uid: str, comment_uid: str, body: dict[str, Any], store: Store = Depends(get_store)):
    text = _text(body)
    _require_owner(store, uid, comment_uid)
    result = store.update_comment(uid, comment_uid, text)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
    return result


@router.post("/artefacts/{uid}/comments/{comment_uid}/resolve")
def resolve_artefact_comment(uid: str, comment_uid: str, body: dict[str, Any] = None, store: Store = Depends(get_store)):
    resolved = (body or {}).get("resolved", True)
    result = store.resolve_comment(uid, comment_uid, resolved)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
    return result


@router.delete("/artefacts/{uid}/comments/{comment_uid}")
def delete_artefact_comment(uid: str, comment_uid: str, store: Store = Depends(get_store)):
    _require_owner(store, uid, comment_uid)
    ok = store.delete_comment(uid, comment_uid)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
    return {"deleted": comment_uid}


@router.get("/requirements/{uid}/comments")
def get_comments(uid: ReqUid, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    return store.get_comments(uid)


@router.post("/requirements/{uid}/comments", status_code=201)
def add_comment(uid: ReqUid, body: dict[str, Any], store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    text = _text(body)
    author = body.get("author") if isinstance(body.get("author"), str) else "anonymous"
    reply_to = body.get("reply_to")
    comment = store.add_comment(uid, text, author, reply_to=reply_to)
    publish_event(store, "comment_added", {"uid": uid, "comment_uid": comment["uid"], "author": comment["author"]})
    return comment


@router.put("/requirements/{uid}/comments/{comment_uid}")
def update_comment(uid: ReqUid, comment_uid: str, body: dict[str, Any], store: Store = Depends(get_store)):
    text = _text(body)
    _require_owner(store, uid, comment_uid)
    result = store.update_comment(uid, comment_uid, text)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
    return result


@router.post("/requirements/{uid}/comments/{comment_uid}/resolve")
def resolve_comment(uid: ReqUid, comment_uid: str, body: dict[str, Any] = None, store: Store = Depends(get_store)):
    resolved = (body or {}).get("resolved", True)
    result = store.resolve_comment(uid, comment_uid, resolved)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
    return result


@router.delete("/requirements/{uid}/comments/{comment_uid}")
def delete_comment(uid: ReqUid, comment_uid: str, store: Store = Depends(get_store)):
    _require_owner(store, uid, comment_uid)
    ok = store.delete_comment(uid, comment_uid)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
    return {"deleted": comment_uid}
