"""
reqtool.routers.principles
==========================
FastAPI router for principle endpoints.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException

from reqtool.store import Store
import copy

from reqtool.git_ops import has_conflicts, stage_file, unstage_file, commit as git_commit
from reqtool.models import CommitRequest, CreatePrincipleRequest, UpdatePrincipleRequest
from .deps import get_store, not_found, conflict

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
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "A commit message is required"})
    snapshot = copy.deepcopy(p)
    path = store.principle_path(uid)
    try:
        store.update_principle(
            uid, {},
            increment=body.increment or "patch",
            summary=message,
            change_ref=body.change_ref,
        )
        stage_file(store.root, path)
        # Only this file is committed and nothing is written afterwards, so the tree stays clean.
        sha = git_commit(
            store.root, message,
            store.config.git.commit_name, store.config.git.commit_email,
            paths=[path],
        )
        p = store.get_principle(uid)
        return {"commit_sha": sha, "version": p.get("version", "") if p else ""}
    except RuntimeError as exc:
        store.restore_principle(uid, snapshot)
        unstage_file(store.root, path)
        raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})
