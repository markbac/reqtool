"""
reqtool.routers.decisions
========================
FastAPI router for Decision Record (ADR) endpoints.
"""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from reqtool.store import Store
from reqtool.git_ops import has_conflicts, stage_file, commit as git_commit
from reqtool.models import CommitRequest, CreateDecisionRequest, UpdateDecisionRequest, ResolveRequest
from reqtool.fileio import utcnow_iso, save_yaml
from .deps import get_store, not_found, conflict

log = logging.getLogger(__name__)

router = APIRouter(tags=["decisions"])


@router.get("/decisions")
def list_decisions(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    owner: Optional[str] = None,
    store: Store = Depends(get_store),
):
    results = []
    for item in store.decisions.values():
        if item.get("deleted"):
            continue
        if status and item.get("status") != status:
            continue
        if priority and item.get("priority") != priority:
            continue
        if owner and item.get("owner") != owner:
            continue
        d = dict(item)
        d["affected_requirements"] = store.compute_affected_requirements(item["uid"])
        results.append(d)
    return results


@router.get("/decisions/{uid}")
def get_decision(uid: str, store: Store = Depends(get_store)):
    d = store.get_decision(uid)
    if d is None:
        raise not_found(uid)
    result = dict(d)
    result["affected_requirements"] = store.compute_affected_requirements(uid)
    return result


@router.post("/decisions", status_code=201)
def create_decision(body: CreateDecisionRequest, store: Store = Depends(get_store)):
    return store.create_decision(body.model_dump(exclude_none=True))


@router.put("/decisions/{uid}")
def update_decision(uid: str, body: UpdateDecisionRequest, store: Store = Depends(get_store)):
    result = store.update_decision(uid, body.model_dump(exclude_none=True), summary="Updated via API")
    if result is None:
        raise not_found(uid)
    return result


@router.delete("/decisions/{uid}")
def delete_decision(uid: str, store: Store = Depends(get_store)):
    result = store.delete_decision(uid)
    if result is None:
        raise not_found(uid)
    return result


@router.post("/decisions/{uid}/commit")
def commit_decision(uid: str, body: CommitRequest, store: Store = Depends(get_store)):
    d = store.get_decision(uid)
    if d is None:
        raise not_found(uid)
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    try:
        path = store.decision_path(uid)
        store.update_decision(
            uid, {},
            increment=body.increment or "patch",
            summary=body.message or "Committed via UI",
            change_ref=body.change_ref,
        )
        stage_file(store.root, path)
        sha = git_commit(
            store.root, body.message,
            store.config.git.commit_name, store.config.git.commit_email,
        )
        d = store.get_decision(uid)
        if d and d.get("history"):
            d["history"][-1]["commit_sha"] = sha[:7]
            save_yaml(path, d)
        return {"commit_sha": sha, "version": d.get("version", "") if d else ""}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})


@router.post("/decisions/{uid}/resolve")
def resolve_decision(uid: str, body: ResolveRequest, store: Store = Depends(get_store)):
    d = store.get_decision(uid)
    if d is None:
        raise not_found(uid)
    content = dict(d.get("content", {}))
    content["resolution"] = body.resolution
    status = "accepted" if d.get("type") == "decision" else "resolved"
    result = store.update_decision(uid, {
        "status": status,
        "content": content,
    }, increment="minor", summary=f"Resolved by {body.resolved_by}")
    return result
