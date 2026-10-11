"""
reqtool.routers.decisions
========================
One router for the decision aggregate. ``/decisions`` serves every record; ``/tbds`` is the same
router limited to ``type: tbd`` (kept for existing clients).
"""

from __future__ import annotations

import copy
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from reqtool.store import Store
from reqtool.models import CommitRequest, CreateDecisionRequest, UpdateDecisionRequest, ResolveRequest
from .auth import get_current_user
from reqtool.fileio import utcnow_iso
from .deps import get_store, not_found, commit_artefact

log = logging.getLogger(__name__)

router = APIRouter()


def _matches(item: dict, kind: Optional[str]) -> bool:
    return kind is None or item.get("type", "decision") == kind


def _build(prefix: str, kind: Optional[str], tag: str) -> None:
    """Register the CRUD, commit and resolve routes under ``prefix``."""
    label = "TBD" if kind == "tbd" else "decision"

    def fetch(store: Store, uid: str) -> dict:
        item = store.get_decision(uid)
        if item is None or not _matches(item, kind):
            raise not_found(uid)
        return item

    @router.get(prefix, tags=[tag], name=f"list_{tag}")
    def list_items(status: Optional[str] = None, priority: Optional[str] = None, owner: Optional[str] = None,
                   store: Store = Depends(get_store)):
        results = []
        for item in store.decision_map().values():
            if item.get("deleted") or not _matches(item, kind):
                continue
            if (status and item.get("status") != status) or (priority and item.get("priority") != priority) \
                    or (owner and item.get("owner") != owner):
                continue
            d = dict(item)
            d["affected_requirements"] = store.compute_affected_requirements(item["uid"])
            results.append(d)
        return results

    @router.get(prefix + "/{uid}", tags=[tag], name=f"get_{tag}")
    def get_item(uid: str, store: Store = Depends(get_store)):
        result = dict(fetch(store, uid))
        result["affected_requirements"] = store.compute_affected_requirements(uid)
        # The link between an open question and the decision it became, shown from both ends.
        brief = lambda d: {"uid": d["uid"], "id": d.get("id"), "title": d.get("title", ""), "type": d.get("type", "decision")}  # noqa: E731
        target = store.get_decision(result["resolution_ref"]) if result.get("resolution_ref") else None
        result["resolved_into"] = brief(target) if target and not target.get("deleted") else None
        result["resolves"] = [brief(d) for d in store.decision_map().values()
                              if not d.get("deleted") and d.get("resolution_ref") == uid]
        return result

    @router.post(prefix, status_code=201, tags=[tag], name=f"create_{tag}")
    def create_item(body: CreateDecisionRequest, store: Store = Depends(get_store)):
        fields = body.model_dump(exclude_none=True)
        return store.create_tbd(fields) if kind == "tbd" else store.create_decision(fields)

    @router.put(prefix + "/{uid}", tags=[tag], name=f"update_{tag}")
    def update_item(uid: str, body: UpdateDecisionRequest, store: Store = Depends(get_store)):
        fetch(store, uid)
        return store.update_decision(uid, body.model_dump(exclude_none=True), summary="Updated via API")

    @router.delete(prefix + "/{uid}", tags=[tag], name=f"delete_{tag}")
    def delete_item(uid: str, store: Store = Depends(get_store)):
        fetch(store, uid)
        return store.delete_decision(uid)

    @router.post(prefix + "/{uid}/commit", tags=[tag], name=f"commit_{tag}")
    def commit_item(uid: str, body: CommitRequest, store: Store = Depends(get_store)):
        snapshot = copy.deepcopy(fetch(store, uid))
        return commit_artefact(
            store, body, store.decision_path(uid),
            bump=lambda message: store.update_decision(
                uid, {}, increment=body.increment or "patch", summary=message, change_ref=body.change_ref),
            undo=lambda: store.restore_decision(uid, snapshot),
            version=lambda: (store.get_decision(uid) or {}).get("version", ""))

    @router.post(prefix + "/{uid}/resolve", tags=[tag], name=f"resolve_{tag}")
    def resolve_item(uid: str, body: ResolveRequest, user: dict = Depends(get_current_user),
                     store: Store = Depends(get_store)):
        """Record the outcome: decision text (required), rationale, an optional linked decision/ADR."""
        d = fetch(store, uid)
        text = (body.decision_text() or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail={"error": "decision_required",
                                "message": f"A {label} cannot be resolved without a decision text"})
        if body.linked_decision:
            linked = store.get_decision(body.linked_decision)
            if linked is None or linked.get("deleted") or body.linked_decision == uid:
                raise HTTPException(status_code=422, detail={"error": "bad_link",
                                    "message": f"Linked decision {body.linked_decision} does not exist"})
        # The resolver is the logged-in user when there is a login; otherwise the name given (local mode).
        resolver = user["username"] if user.get("authenticated") else (body.resolved_by or "unknown")
        content = dict(d.get("content", {}))
        content["resolution"] = text
        if body.rationale:
            content["rationale"] = body.rationale
        fields = {
            "status": "accepted" if d.get("type") == "decision" else "resolved",
            "content": content, "resolved_by": resolver, "resolved_at": utcnow_iso(),
            "resolution_ref": body.linked_decision or None,
        }
        return store.update_decision(uid, fields, increment="minor", summary=f"Resolved by {resolver}")


_build("/decisions", None, "decisions")
_build("/tbds", "tbd", "tbds")
