"""
reqtool.routers.tbds
===================
FastAPI router for TBD endpoints.
"""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from reqtool.store import Store
from reqtool.git_ops import has_conflicts, stage_file, commit as git_commit
from reqtool.models import CommitRequest, CreateTBDRequest, UpdateTBDRequest, ResolveRequest
from reqtool.fileio import utcnow_iso, save_yaml
from .deps import get_store, not_found, conflict

log = logging.getLogger(__name__)

router = APIRouter(tags=["tbds"])


@router.get("/tbds")
def list_tbds(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    owner: Optional[str] = None,
    store: Store = Depends(get_store),
):
    results = []
    for tbd in store.tbds.values():
        if tbd.get("deleted"):
            continue
        if status and tbd.get("status") != status:
            continue
        if priority and tbd.get("priority") != priority:
            continue
        if owner and tbd.get("owner") != owner:
            continue
        t = dict(tbd)
        t["affected_requirements"] = store.compute_affected_requirements(tbd["uid"])
        results.append(t)
    return results


@router.get("/tbds/{uid}")
def get_tbd(uid: str, store: Store = Depends(get_store)):
    t = store.get_tbd(uid)
    if t is None:
        raise not_found(uid)
    result = dict(t)
    result["affected_requirements"] = store.compute_affected_requirements(uid)
    return result


@router.post("/tbds", status_code=201)
def create_tbd(body: CreateTBDRequest, store: Store = Depends(get_store)):
    return store.create_tbd(body.model_dump(exclude_none=True))


@router.put("/tbds/{uid}")
def update_tbd(uid: str, body: UpdateTBDRequest, store: Store = Depends(get_store)):
    result = store.update_tbd(uid, body.model_dump(exclude_none=True), summary="Updated via API")
    if result is None:
        raise not_found(uid)
    return result


@router.delete("/tbds/{uid}")
def delete_tbd(uid: str, store: Store = Depends(get_store)):
    result = store.delete_tbd(uid)
    if result is None:
        raise not_found(uid)
    return result


@router.post("/tbds/{uid}/commit")
def commit_tbd(uid: str, body: CommitRequest, store: Store = Depends(get_store)):
    t = store.get_tbd(uid)
    if t is None:
        raise not_found(uid)
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    try:
        path = store.tbd_path(uid)
        store.update_tbd(
            uid, {},
            increment=body.increment or "patch",
            summary=body.message or "Committed via UI",
            change_ref=body.change_ref,
        )
        stage_file(store.root, path)
        sha = git_commit(
            store.root, body.message,
            store.config.git.commit_name, store.config.git.commit_email,
            paths=[path],
        )
        t = store.get_tbd(uid)
        return {"commit_sha": sha, "version": t.get("version", "") if t else ""}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})


@router.post("/tbds/{uid}/resolve")
def resolve_tbd(uid: str, body: ResolveRequest, store: Store = Depends(get_store)):
    t = store.get_tbd(uid)
    if t is None:
        raise not_found(uid)
    content = dict(t.get("content", {}))
    content["resolution"] = body.resolution
    result = store.update_tbd(uid, {
        "status": "resolved",
        "content": content,
    }, increment="minor", summary=f"Resolved by {body.resolved_by}")
    return result
