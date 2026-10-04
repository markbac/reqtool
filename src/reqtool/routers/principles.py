"""
reqtool.routers.principles
==========================
FastAPI router for principle endpoints.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends

from reqtool.store import Store

from reqtool.models import CommitRequest, CreatePrincipleRequest, UpdatePrincipleRequest
from .deps import get_store, not_found, commit_artefact

log = logging.getLogger(__name__)

router = APIRouter(tags=["principles"])


@router.get("/principles")
def list_principles(store: Store = Depends(get_store)):
    return [p for p in store.principles.values() if not p.get("deleted")]


@router.get("/principles/{uid}")
def get_principle(uid: str, store: Store = Depends(get_store)):
    p = store.get_principle(uid)
    if p is None:
        raise not_found(uid)
    return p


@router.post("/principles", status_code=201)
def create_principle(body: CreatePrincipleRequest, store: Store = Depends(get_store)):
    return store.create_principle(body.model_dump(exclude_none=True))


@router.put("/principles/{uid}")
def update_principle(uid: str, body: UpdatePrincipleRequest, store: Store = Depends(get_store)):
    result = store.update_principle(uid, body.model_dump(exclude_none=True), summary="Updated via API")
    if result is None:
        raise not_found(uid)
    return result


@router.delete("/principles/{uid}")
def delete_principle(uid: str, store: Store = Depends(get_store)):
    result = store.delete_principle(uid)
    if result is None:
        raise not_found(uid)
    return result


@router.post("/principles/{uid}/commit")
def commit_principle(uid: str, body: CommitRequest, store: Store = Depends(get_store)):
    p = store.get_principle(uid)
    if p is None:
        raise not_found(uid)
    return commit_artefact(
        store, body, store.principle_path(uid),
        bump=lambda message: store.update_principle(
            uid, {}, increment=body.increment or "patch", summary=message, change_ref=body.change_ref),
        undo=lambda: store.restore_principle(uid, p),
        version=lambda: (store.get_principle(uid) or {}).get("version", ""))