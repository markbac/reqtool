"""
reqtool.routers.requirements
============================
FastAPI router for requirement endpoints.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response

from reqtool.store import Store
from reqtool.git_ops import git_log
from reqtool.models import (
    CommitRequest, ApproveRequest, BulkUpdateRequest,
    CreateRequirementRequest, UpdateRequirementRequest,
    AddACRequest, UpdateACRequest,
)
from reqtool.services.requirements import RequirementService, changed_fields
from .deps import get_store, not_found, publish_event, ReqUid
from .auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(tags=["requirements"])


def get_service(store: Store = Depends(get_store)) -> RequirementService:
    return RequirementService(store, partial(publish_event, store))


@router.get("/requirements")
def list_requirements(
    product: Optional[str] = None,
    domain: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    req_type: Optional[str] = None,
    owner: Optional[str] = None,
    tag: Optional[str] = None,
    deleted: bool = False,
    limit: Optional[int] = Query(None, ge=1, le=10000, description="Maximum items to return (default: all)"),
    offset: int = Query(0, ge=0, description="Items to skip, after sorting by id"),
    response: Response = None,
    store: Store = Depends(get_store),
):
    """List requirements (summary fields). The matching total is always sent in ``X-Total-Count``."""
    results = []
    for req in store.requirement_map().values():
        if not deleted and req.get("deleted"):
            continue
        if deleted and not req.get("deleted"):
            continue
        if domain and req.get("domain") != domain:
            continue
        if status and req.get("status") != status:
            continue
        if priority and req.get("priority") != priority:
            continue
        if req_type and req.get("req_type") != req_type:
            continue
        if owner and req.get("owner") != owner:
            continue
        if tag and tag not in req.get("tags", []):
            continue
        results.append({
            "uid": req.get("uid"),
            "id": req.get("id"),
            "title": req.get("title"),
            "status": req.get("status"),
            "priority": req.get("priority"),
            "req_type": req.get("req_type"),
            "domain": req.get("domain"),
            "owner": req.get("owner"),
            "version": req.get("version"),
            "parentId": req.get("parentId"),
        })
    results.sort(key=lambda r: r.get("id") or "")
    response.headers["X-Total-Count"] = str(len(results))
    if limit is not None:
        return results[offset:offset + limit]
    return results[offset:] if offset else results


@router.get("/requirements/tree")
def requirements_tree(
    product: str = Query(...),
    variant: Optional[str] = None,
    store: Store = Depends(get_store),
):
    return store.build_tree(product, variant)


@router.get("/requirements/{uid}")
def get_requirement(uid: ReqUid, store: Store = Depends(get_store)):
    """Fetch by UID or by human ID (for example ``FR-042``)."""
    req = store.get_requirement(store.resolve_uid(uid) or uid)
    if req is None:
        raise not_found(uid)
    return req


@router.get("/requirements/{uid}/progress")
def get_requirement_progress(uid: ReqUid, store: Store = Depends(get_store)):
    """Return hierarchical progress percentage and estimate completion metrics."""
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    return store.compute_progress_rollup(uid)


@router.post("/requirements/bulk")
def bulk_update_requirements(body: BulkUpdateRequest, service: RequirementService = Depends(get_service)):
    """Update a set of fields across multiple requirements at once (same guards as single updates)."""
    return service.bulk_update(body.uids, body.fields, body.increment, body.summary)


@router.post("/requirements/{uid}/clone", status_code=201)
def clone_requirement(uid: ReqUid, new_id: str = "", service: RequirementService = Depends(get_service)):
    """Duplicate a requirement, clearing history and resetting version."""
    return service.clone(uid, new_id)


@router.post("/requirements/{uid}/relationships/{rel_index}/clear-suspect")
def clear_suspect_link(uid: ReqUid, rel_index: int, store: Store = Depends(get_store)):
    """Acknowledge and clear suspect flag on a relationship link."""
    res = store.clear_suspect_link(uid, rel_index)
    if not res:
        raise not_found(f"Requirement '{uid}' or relationship index '{rel_index}' not found")
    return {"status": "cleared", "uid": uid, "rel_index": rel_index}


@router.post("/requirements", status_code=201)
def create_requirement(body: CreateRequirementRequest, service: RequirementService = Depends(get_service)):
    return service.create(body.model_dump(exclude_none=True))


@router.put("/requirements/{uid}")
def update_requirement(
    uid: str,
    body: UpdateRequirementRequest,
    if_version: Optional[str] = None,
    service: RequirementService = Depends(get_service),
):
    """Update a requirement. Pass if_version=<current_version> to detect concurrent edits."""
    return service.update(uid, changed_fields(body.model_dump(exclude_unset=True)), if_version)


@router.delete("/requirements/{uid}")
def delete_requirement(uid: ReqUid, service: RequirementService = Depends(get_service)):
    return service.delete(uid)


@router.post("/requirements/{uid}/commit")
def commit_requirement(uid: ReqUid, body: CommitRequest, service: RequirementService = Depends(get_service)):
    return service.commit(uid, body.message, body.increment, body.change_ref)


@router.post("/requirements/{uid}/approve")
def approve_requirement(
    uid: str, body: ApproveRequest,
    user: dict = Depends(get_current_user),
    service: RequirementService = Depends(get_service),
):
    return service.approve(uid, body.approved_by, body.content_hash, user)


def _attach_commit_shas(history: list[dict], git_entries: list[dict]) -> list[dict]:
    """Display-only: pair history entries with the git commit that carries the same message.

    The SHA is no longer stored in the YAML (it would dirty the file after the
    commit), so it is derived from git log here, newest first.
    """
    pool = list(git_entries or [])
    out = []
    for entry in reversed(history or []):
        e = dict(entry)
        if not e.get("commit_sha"):
            for i, g in enumerate(pool):
                if g.get("subject") == e.get("summary"):
                    e["commit_sha"] = str(g.get("sha", ""))[:7] or None
                    pool.pop(i)
                    break
        out.append(e)
    return list(reversed(out))


@router.get("/requirements/{uid}/commits")
def requirement_commits(uid: ReqUid, store: Store = Depends(get_store)):
    """Development commits linked to this requirement from GitHub push webhooks (not part of its content)."""
    if store.get_requirement(uid) is None:
        raise not_found(uid)
    from reqtool.github_sync import load_commit_links
    return load_commit_links(store, uid)


@router.get("/requirements/{uid}/history")
def requirement_history(uid: ReqUid, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    file_path = store.req_path(uid)
    git_entries = git_log(store.root, file_path)
    return {
        "in_file": _attach_commit_shas(req.get("history", []), git_entries),
        "git": git_entries,
    }


@router.get("/requirements/{uid}/relationships")
def requirement_relationships(uid: ReqUid, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    outgoing = req.get("relationships", [])
    incoming = []
    for other_uid, other in store.requirement_map().items():
        if other_uid == uid:
            continue
        for rel in other.get("relationships", []):
            if rel.get("target", {}).get("uid") == uid:
                incoming.append({"source_uid": other_uid, "source_id": other.get("id"), "type": rel.get("type")})
    return {"outgoing": outgoing, "incoming": incoming}


@router.post("/requirements/{uid}/ac", status_code=201)
def add_ac(uid: ReqUid, body: AddACRequest, service: RequirementService = Depends(get_service)):
    return service.add_criterion(uid, body.text, body.id, body.links)


@router.put("/requirements/{uid}/ac/{ac_uid}")
def update_ac(uid: ReqUid, ac_uid: str, body: UpdateACRequest, service: RequirementService = Depends(get_service)):
    return service.update_criterion(uid, ac_uid, body.model_dump(exclude_none=True))


@router.delete("/requirements/{uid}/ac/{ac_uid}")
def delete_ac(uid: ReqUid, ac_uid: str, service: RequirementService = Depends(get_service)):
    return service.delete_criterion(uid, ac_uid)


@router.get("/requirements/{uid}/impact")
def requirement_impact(uid: ReqUid, store: Store = Depends(get_store)):
    """Return the transitive downstream impact closure for a requirement."""
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    return store.compute_impact(uid)


@router.post("/requirements/{uid}/transition")
def transition_requirement(uid: ReqUid, body: dict, service: RequirementService = Depends(get_service)):
    """Transition a requirement to a new status with workflow guard enforcement."""
    return service.transition(uid, body.get("to_state", ""))


@router.get("/requirements/{uid}/transitions")
def requirement_transitions(uid: ReqUid, service: RequirementService = Depends(get_service)):
    """Where the item can move next, what each move needs, and which of those needs are still unmet."""
    return service.transitions(uid)


@router.get("/requirements/{uid}/rollup")
def estimate_rollup(uid: ReqUid, store: Store = Depends(get_store)):
    """Return the rolled-up estimate sum for all direct children."""
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    rollup = store.compute_estimate_rollup(uid)
    return {"uid": uid, "estimate_rollup": rollup, "estimate_unit": store.repo_enums.estimate_unit}
