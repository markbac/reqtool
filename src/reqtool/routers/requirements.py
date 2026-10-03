"""
reqtool.routers.requirements
============================
FastAPI router for requirement endpoints.
"""

from __future__ import annotations

import copy
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from reqtool.store import Store, ParentCycle, HierarchyViolation, RelationshipViolation, DuplicateId
from reqtool.git_ops import has_conflicts, stage_file, commit as git_commit, git_log
from reqtool.models import (
    CommitRequest, ApproveRequest, BulkUpdateRequest,
    CreateRequirementRequest, UpdateRequirementRequest,
    AddACRequest, UpdateACRequest,
)
from reqtool.fileio import utcnow_iso, uuid7, save_yaml
from .deps import get_store, not_found, conflict, publish_event
from .auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(tags=["requirements"])


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
    store: Store = Depends(get_store),
):
    results = []
    for req in store.requirements.values():
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
    return sorted(results, key=lambda r: r.get("id", ""))


@router.get("/requirements/tree")
def requirements_tree(
    product: str = Query(...),
    variant: Optional[str] = None,
    store: Store = Depends(get_store),
):
    return store.build_tree(product, variant)


@router.get("/requirements/{uid}")
def get_requirement(uid: str, store: Store = Depends(get_store)):
    """Fetch by UID or by human ID (for example ``FR-042``)."""
    req = store.get_requirement(store.resolve_uid(uid) or uid)
    if req is None:
        raise not_found(uid)
    return req


@router.get("/requirements/{uid}/progress")
def get_requirement_progress(uid: str, store: Store = Depends(get_store)):
    """Return hierarchical progress percentage and estimate completion metrics."""
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    return store.compute_progress_rollup(uid)


def _publish_change(store: Store, uid: str, old_status, result: dict) -> None:
    """One event per update: status_changed if the status moved, else requirement_updated."""
    if result.get("status") != old_status:
        publish_event(store, "status_changed", {
            "uid": uid, "id": result.get("id"), "from": old_status, "to": result.get("status"),
        })
    else:
        publish_event(store, "requirement_updated", {"uid": uid, "id": result.get("id")})


@router.post("/requirements/bulk")
def bulk_update_requirements(body: BulkUpdateRequest, store: Store = Depends(get_store)):
    """Update a set of fields across multiple requirements at once.

    Same guards as single updates: no writes while the tree has merge conflicts,
    and a status change must be a legal workflow transition for each item.
    """
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    updated = []
    failed = []
    errors = {}
    changes: list[tuple[str, object, dict]] = []
    new_status = body.fields.get("status") if isinstance(body.fields, dict) else None
    with store._lock:  # make the check-then-update atomic per request
        for uid in body.uids:
            existing = store.get_requirement(uid)
            if existing is None:
                failed.append(uid)
                errors[uid] = "not found"
                continue
            if new_status and new_status != existing.get("status"):
                error = store.validate_transition(existing, new_status)
                if error:
                    failed.append(uid)
                    errors[uid] = error
                    continue
            old_status = existing.get("status")
            try:
                result = store.update_requirement(
                    uid, body.fields,
                    increment=body.increment,
                    summary=body.summary,
                )
            except (ParentCycle, HierarchyViolation, RelationshipViolation, DuplicateId) as exc:
                failed.append(uid)
                errors[uid] = str(exc)
                continue
            if result:
                updated.append(uid)
                changes.append((uid, old_status, dict(result)))
            else:
                failed.append(uid)
    for uid, old_status, result in changes:
        _publish_change(store, uid, old_status, result)
    return {"updated": updated, "failed": failed, "count": len(updated), "errors": errors}


@router.post("/requirements/{uid}/clone", status_code=201)
def clone_requirement(uid: str, new_id: str = "", store: Store = Depends(get_store)):
    """Duplicate a requirement, clearing history and resetting version."""
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    src = store.get_requirement(uid)
    if src is None:
        raise not_found(uid)
    fields = copy.deepcopy(src)
    for key in ("uid", "content_hash", "created", "last_modified", "history",
                "version", "schema_version", "tool_version", "type"):
        fields.pop(key, None)
    if new_id:
        fields["id"] = new_id
    else:
        base = src.get("id", "REQ") + "-COPY"
        fields["id"], n = base, 1
        while store.resolve_uid(fields["id"]):  # keep clones unique
            n += 1
            fields["id"] = f"{base}{n}"
    fields["title"] = src.get("title", "") + " (copy)"
    fields["status"] = "draft"
    fields["approval"] = {"status": "draft", "approved_by": None, "approved_date": None}
    fields["verification"] = {"status": "not_started", "verified_date": None, "note": ""}
    created = store.create_requirement(fields)
    publish_event(store, "requirement_created", {"uid": created["uid"], "id": created.get("id"), "req_type": created.get("req_type")})
    return created


@router.post("/requirements/{uid}/relationships/{rel_index}/clear-suspect")
def clear_suspect_link(uid: str, rel_index: int, store: Store = Depends(get_store)):
    """Acknowledge and clear suspect flag on a relationship link."""
    res = store.clear_suspect_link(uid, rel_index)
    if not res:
        raise not_found(f"Requirement '{uid}' or relationship index '{rel_index}' not found")
    return {"status": "cleared", "uid": uid, "rel_index": rel_index}


@router.post("/requirements", status_code=201)
def create_requirement(body: CreateRequirementRequest, store: Store = Depends(get_store)):
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    created = store.create_requirement(body.model_dump(exclude_none=True))
    publish_event(store, "requirement_created", {"uid": created["uid"], "id": created.get("id"), "req_type": created.get("req_type")})
    return created


@router.put("/requirements/{uid}")
def update_requirement(
    uid: str,
    body: UpdateRequirementRequest,
    if_version: Optional[str] = None,
    store: Store = Depends(get_store),
):
    """Update a requirement. Pass if_version=<current_version> to detect concurrent edits."""
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    existing = store.get_requirement(uid)
    if existing is None:
        raise not_found(uid)
    if if_version and existing.get("version") != if_version:
        raise HTTPException(status_code=409, detail={
            "error": "version_conflict",
            "message": f"Requirement was modified since you loaded it "
                       f"(your version: {if_version}, current: {existing.get('version')}). "
                       "Reload and re-apply your changes.",
            "current_version": existing.get("version"),
            "your_version": if_version,
        })
    old_status = existing.get("status")
    new_status = body.model_dump(exclude_none=True).get("status")
    if new_status and new_status != old_status:
        error = store.validate_transition(existing, new_status)
        if error:
            raise HTTPException(status_code=409, detail={"error": "workflow_guard", "message": error})
    result = store.update_requirement(uid, body.model_dump(exclude_none=True), summary="Updated via API")
    if result is None:
        raise not_found(uid)
    _publish_change(store, uid, old_status, result)
    return result


@router.delete("/requirements/{uid}")
def delete_requirement(uid: str, store: Store = Depends(get_store)):
    result = store.delete_requirement(uid)
    if result is None:
        raise not_found(uid)
    publish_event(store, "requirement_deleted", {"uid": uid, "id": result.get("id")})
    return result


@router.post("/requirements/{uid}/commit")
def commit_requirement(uid: str, body: CommitRequest, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    try:
        file_path = store.req_path(uid)
        store.update_requirement(
            uid, {},
            increment=body.increment or "patch",
            summary=body.message or "Committed via UI",
            change_ref=body.change_ref,
        )
        stage_file(store.root, file_path)
        # Commit ONLY this requirement's file. Nothing is written back into the
        # YAML afterwards, so the working tree is clean and the file hash/audit
        # record cannot drift from what was committed; the SHA is in git history.
        sha = git_commit(
            store.root, body.message,
            store.config.git.commit_name, store.config.git.commit_email,
            paths=[file_path],
        )
        req = store.get_requirement(uid)
        return {"commit_sha": sha, "version": req.get("version", "") if req else ""}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})


@router.post("/requirements/{uid}/approve")
def approve_requirement(
    uid: str, body: ApproveRequest,
    user: dict = Depends(get_current_user),
    store: Store = Depends(get_store),
):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    # Who approves is decided by the login, never by the request body.
    if user["authenticated"]:
        if user["role"] not in ("admin", "editor"):
            raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Your role may not approve requirements"})
        if body.approved_by and body.approved_by != user["username"]:
            raise HTTPException(status_code=403, detail={
                "error": "forbidden",
                "message": f"approved_by must be the logged-in user '{user['username']}'",
            })
        approver, verified = user["username"], True
    else:
        approver, verified = body.approved_by, False  # local single-user mode
    if req.get("status") != "approved":
        error = store.validate_transition(req, "approved")
        if error:
            raise HTTPException(status_code=409, detail={"error": "workflow_guard", "message": error})
    result = store.approve_requirement(uid, approver, identity_verified=verified)
    if result is None:
        raise not_found(uid)
    publish_event(store, "requirement_approved", {
        "uid": uid, "id": req.get("id"), "approved_by": approver,
        "signature": result["approval"]["signature"],
    })
    return result

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


@router.get("/requirements/{uid}/history")
def requirement_history(uid: str, store: Store = Depends(get_store)):
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
def requirement_relationships(uid: str, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    outgoing = req.get("relationships", [])
    incoming = []
    for other_uid, other in store.requirements.items():
        if other_uid == uid:
            continue
        for rel in other.get("relationships", []):
            if rel.get("target", {}).get("uid") == uid:
                incoming.append({"source_uid": other_uid, "source_id": other.get("id"), "type": rel.get("type")})
    return {"outgoing": outgoing, "incoming": incoming}


@router.post("/requirements/{uid}/ac", status_code=201)
def add_ac(uid: str, body: AddACRequest, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    ac_uid = uuid7()
    new_ac = {
        "uid": ac_uid,
        "id": body.id or f"{req.get('id', '')}__AC-{ac_uid[:8]}",
        "text": body.text,
        "links": body.links or [],
    }
    acs = list(req.get("acceptance_criteria", []))
    acs.append(new_ac)
    result = store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Added acceptance criterion")
    publish_event(store, "requirement_updated", {"uid": uid, "id": req.get("id")})
    return result


@router.put("/requirements/{uid}/ac/{ac_uid}")
def update_ac(uid: str, ac_uid: str, body: UpdateACRequest, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    acs = list(req.get("acceptance_criteria", []))
    for i, ac in enumerate(acs):
        if ac.get("uid") == ac_uid:
            acs[i] = {**ac, **body.model_dump(exclude_none=True)}
            result = store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Updated acceptance criterion")
            publish_event(store, "requirement_updated", {"uid": uid, "id": req.get("id")})
            return result
    raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"AC '{ac_uid}' not found"})


@router.delete("/requirements/{uid}/ac/{ac_uid}")
def delete_ac(uid: str, ac_uid: str, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    acs = [ac for ac in req.get("acceptance_criteria", []) if ac.get("uid") != ac_uid]
    result = store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Removed acceptance criterion")
    publish_event(store, "requirement_updated", {"uid": uid, "id": req.get("id")})
    return result


@router.get("/requirements/{uid}/impact")
def requirement_impact(uid: str, store: Store = Depends(get_store)):
    """Return the transitive downstream impact closure for a requirement."""
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    return store.compute_impact(uid)


@router.post("/requirements/{uid}/transition")
def transition_requirement(uid: str, body: dict, store: Store = Depends(get_store)):
    """Transition a requirement to a new status with workflow guard enforcement."""
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    to_state = body.get("to_state", "")
    if not to_state:
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "to_state is required"})
    error = store.validate_transition(req, to_state)
    if error:
        raise HTTPException(status_code=409, detail={"error": "workflow_guard", "message": error})
    old_status = req.get("status")
    result = store.update_requirement(uid, {"status": to_state}, summary=f"Transitioned to {to_state}")
    publish_event(store, "status_changed", {
        "uid": uid, "id": req.get("id"), "from": old_status, "to": to_state,
    })
    return result


@router.get("/requirements/{uid}/rollup")
def estimate_rollup(uid: str, store: Store = Depends(get_store)):
    """Return the rolled-up estimate sum for all direct children."""
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    rollup = store.compute_estimate_rollup(uid)
    return {"uid": uid, "estimate_rollup": rollup, "estimate_unit": store.repo_enums.estimate_unit}
