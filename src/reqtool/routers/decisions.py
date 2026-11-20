"""
reqtool.routers.decisions
========================
One router for decisions. ``/decisions`` serves every record. A decision is pending (status
``proposed``) until it is accepted, rejected or superseded; open questions are pending decisions (#371).
``/tbds`` is a deprecated alias that lists and creates pending decisions, kept for one release.
"""

from __future__ import annotations

import copy
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from reqtool.artefacts import PENDING_DECISION_STATUSES, legacy_decision_status
from reqtool.store import Store
from reqtool.models import CommitRequest, CreateDecisionRequest, UpdateDecisionRequest, ResolveRequest
from .auth import get_current_user
from reqtool.fileio import utcnow_iso
from .deps import get_store, not_found, commit_artefact, publish_event

log = logging.getLogger(__name__)

router = APIRouter()


def _matches(item: dict, pending_only: bool) -> bool:
    return not pending_only or item.get("status") in PENDING_DECISION_STATUSES


def accept_decision(store: Store, uid: str, body: ResolveRequest, user: dict) -> dict:
    """Accept a decision: the decision text is required. Requirements that refer to it get a wording note."""
    d = store.get_decision(uid) or {}
    text = (body.decision_text() or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail={"error": "decision_required",
                            "message": "A decision cannot be accepted without the decision text"})
    if body.linked_decision:
        linked = store.get_decision(body.linked_decision)
        if linked is None or linked.get("deleted") or body.linked_decision == uid:
            raise HTTPException(status_code=422, detail={"error": "bad_link",
                                "message": f"Linked decision {body.linked_decision} does not exist"})
    # The person accepting is the logged-in user when there is a login; otherwise the name given (local mode).
    by = user["username"] if user.get("authenticated") else (body.resolved_by or "unknown")
    content = dict(d.get("content", {}))
    content["resolution"] = text
    if body.rationale:
        content["rationale"] = body.rationale
    if body.chosen_option:
        content["chosen_option"] = body.chosen_option
    fields = {"type": "decision", "status": "accepted", "in_progress": False, "content": content,
              "resolved_by": by, "resolved_at": utcnow_iso(), "resolution_ref": body.linked_decision or None}
    result = store.update_decision(uid, fields, increment="minor", summary=f"Accepted by {by}")
    for req_uid in store.requirements_referencing_decision(uid):
        req = store.requirement_map().get(req_uid) or {}
        publish_event(store, "decision_accepted", {"uid": req_uid, "id": req.get("id"), "decision": result.get("id"),
                                                   "decision_uid": uid, "by": by})
    return result


def _build(prefix: str, pending_only: bool, tag: str, deprecated: bool = False) -> None:
    """Register the CRUD, commit, accept and reject routes under ``prefix``."""
    def fetch(store: Store, uid: str) -> dict:
        item = store.get_decision(uid)
        if item is None:
            raise not_found(uid)
        return item

    @router.get(prefix, tags=[tag], name=f"list_{tag}", deprecated=deprecated)
    def list_items(status: Optional[str] = None, priority: Optional[str] = None, owner: Optional[str] = None,
                   store: Store = Depends(get_store)):
        results = []
        for item in store.decision_map().values():
            if item.get("deleted") or not _matches(item, pending_only):
                continue
            if (status and legacy_decision_status(item.get("status")) != legacy_decision_status(status)) \
                    or (priority and item.get("priority") != priority) or (owner and item.get("owner") != owner):
                continue
            d = dict(item)
            d["affected_requirements"] = store.compute_affected_requirements(item["uid"])
            results.append(d)
        return results

    @router.get(prefix + "/{uid}", tags=[tag], name=f"get_{tag}", deprecated=deprecated)
    def get_item(uid: str, store: Store = Depends(get_store)):
        uid = store.resolve_decision(uid) or uid
        result = dict(fetch(store, uid))
        result["affected_requirements"] = store.compute_affected_requirements(uid)
        result["referenced_by"] = store.requirements_referencing_decision(uid)
        reqs = store.requirement_map()
        result["waiting"] = [{"uid": u, "id": reqs[u].get("id"), "title": reqs[u].get("title", ""),
                              "status": reqs[u].get("status")} for u in result["referenced_by"] if u in reqs]
        # The link between an open question and the decision it became, shown from both ends.
        brief = lambda d: {"uid": d["uid"], "id": d.get("id"), "title": d.get("title", ""), "type": d.get("type", "decision")}  # noqa: E731
        target = store.get_decision(result["resolution_ref"]) if result.get("resolution_ref") else None
        result["resolved_into"] = brief(target) if target and not target.get("deleted") else None
        result["resolves"] = [brief(d) for d in store.decision_map().values()
                              if not d.get("deleted") and d.get("resolution_ref") == uid]
        return result

    @router.post(prefix, status_code=201, tags=[tag], name=f"create_{tag}", deprecated=deprecated)
    def create_item(body: CreateDecisionRequest, store: Store = Depends(get_store)):
        fields = body.model_dump(exclude_none=True)
        return store.create_tbd(fields) if pending_only else store.create_decision(fields)

    @router.put(prefix + "/{uid}", tags=[tag], name=f"update_{tag}", deprecated=deprecated)
    def update_item(uid: str, body: UpdateDecisionRequest, store: Store = Depends(get_store)):
        fetch(store, uid)
        fields = body.model_dump(exclude_none=True)
        if "status" in fields:
            fields["status"] = legacy_decision_status(fields["status"])
        return store.update_decision(uid, fields, summary="Updated via API")

    @router.delete(prefix + "/{uid}", tags=[tag], name=f"delete_{tag}", deprecated=deprecated)
    def delete_item(uid: str, store: Store = Depends(get_store)):
        fetch(store, uid)
        return store.delete_decision(uid)

    @router.post(prefix + "/{uid}/commit", tags=[tag], name=f"commit_{tag}", deprecated=deprecated)
    def commit_item(uid: str, body: CommitRequest, store: Store = Depends(get_store)):
        snapshot = copy.deepcopy(fetch(store, uid))
        return commit_artefact(
            store, body, store.decision_path(uid),
            bump=lambda message: store.update_decision(
                uid, {}, increment=body.increment or "patch", summary=message, change_ref=body.change_ref),
            undo=lambda: store.restore_decision(uid, snapshot),
            version=lambda: (store.get_decision(uid) or {}).get("version", ""))

    @router.post(prefix + "/{uid}/accept", tags=[tag], name=f"accept_{tag}", deprecated=deprecated)
    def accept_item(uid: str, body: ResolveRequest, user: dict = Depends(get_current_user),
                    store: Store = Depends(get_store)):
        """Accept the decision: decision text (required), rationale, chosen option, an optional linked decision."""
        fetch(store, uid)
        return accept_decision(store, uid, body, user)

    @router.post(prefix + "/{uid}/resolve", tags=[tag], name=f"resolve_{tag}", deprecated=True)
    def resolve_item(uid: str, body: ResolveRequest, user: dict = Depends(get_current_user),
                     store: Store = Depends(get_store)):
        """Deprecated name for ``accept``."""
        fetch(store, uid)
        return accept_decision(store, uid, body, user)

    @router.post(prefix + "/{uid}/reject", tags=[tag], name=f"reject_{tag}", deprecated=deprecated)
    def reject_item(uid: str, body: ResolveRequest, user: dict = Depends(get_current_user),
                    store: Store = Depends(get_store)):
        """Reject the decision, with the reason in ``decision`` or ``rationale``."""
        d = fetch(store, uid)
        by = user["username"] if user.get("authenticated") else (body.resolved_by or "unknown")
        content = dict(d.get("content", {}))
        reason = (body.decision_text() or body.rationale or "").strip()
        if reason:
            content["rationale"] = reason
        return store.update_decision(uid, {"type": "decision", "status": "rejected", "in_progress": False,
                                           "content": content, "resolved_by": by, "resolved_at": utcnow_iso()},
                                     increment="minor", summary=f"Rejected by {by}")


_build("/decisions", False, "decisions")
_build("/tbds", True, "tbds", deprecated=True)
