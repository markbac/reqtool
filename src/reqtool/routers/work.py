"""
reqtool.routers.work
====================
The Work area's views (#378, #379): the issue queue and the backlog of work items, ranked.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from reqtool import layout
from reqtool.store import Store
from .deps import get_store, not_found

router = APIRouter(prefix="/work", tags=["work"])

LINK_TO_REQUIREMENT = ("satisfies", "implements", "traces_to")


def _live(store: Store, product: Optional[str]) -> dict[str, dict[str, Any]]:
    reqs = store.resolved_requirements(product, None) if product else store.requirement_map()
    return {uid: r for uid, r in reqs.items() if not r.get("deleted")}


@router.get("/issues")
def issue_queue(product: Optional[str] = None, store: Store = Depends(get_store)):
    """Issues waiting for or rejected in triage, and the work items that issues were converted into."""
    live = _live(store, product)
    issues, converted = [], []
    for uid, r in live.items():
        if r.get("req_type") == "issue":
            custom = r.get("custom_fields") or {}
            issues.append({"uid": uid, "id": r.get("id"), "title": r.get("title", ""), "status": r.get("status"),
                           "priority": r.get("priority"), "assignee": r.get("assignee"), "created": r.get("created"),
                           "reporter": custom.get("reporter"), "converted_to": r.get("converted_to")})
        elif (r.get("converted_from") or {}).get("type") == "issue":
            converted.append({"uid": uid, "id": r.get("id"), "title": r.get("title", ""), "status": r.get("status"),
                              "req_type": r.get("req_type"), "converted_from": r["converted_from"].get("id")})
    # Issues closed by the older "raise" flow point at the work item they led to.
    for i in issues:
        target = live.get(i.get("converted_to") or "")
        if target:
            converted.append({"uid": target["uid"], "id": target.get("id"), "title": target.get("title", ""),
                              "status": target.get("status"), "req_type": target.get("req_type"), "converted_from": i["id"]})
    issues = [i for i in issues if not i.get("converted_to")]
    issues.sort(key=lambda i: i.get("created") or "", reverse=True)
    converted.sort(key=lambda c: c.get("id") or "")
    return {"issues": issues, "converted": converted}


@router.get("/backlog")
def backlog(product: Optional[str] = None, store: Store = Depends(get_store)):
    """Work items as a tree (theme down to task), ranked within each parent, with points and roll-ups."""
    live = _live(store, product)
    work = {uid: r for uid, r in live.items()
            if layout.family(r.get("req_type"), store.hierarchy) == "work" and r.get("req_type") != "issue"}
    children: dict[Optional[str], list[dict]] = {}
    for r in work.values():
        parent = r.get("parentId") if r.get("parentId") in work else None
        children.setdefault(parent, []).append(r)
    for kids in children.values():
        kids.sort(key=lambda r: (r.get("rank") if isinstance(r.get("rank"), (int, float)) else float("inf"), r.get("id") or ""))

    def done(r: dict) -> bool:
        wf = store.get_workflow_for_type(r.get("req_type", "story"))
        terminal = {s.id for s in wf.states if getattr(s, "terminal", False)} if wf else set()
        return r.get("status") in (terminal or {"done", "cancelled", "closed"})

    def node(r: dict) -> dict:
        kids = [node(c) for c in children.get(r["uid"], [])]
        links = sum(1 for rel in r.get("relationships") or [] if rel.get("type") in LINK_TO_REQUIREMENT)
        total = sum(k["total_points"] or (k["estimate"] or 0) for k in kids)
        finished = sum(k["done_points"] if k["children"] else ((k["estimate"] or 0) if k["done"] else 0) for k in kids)
        out = {"uid": r["uid"], "id": r.get("id"), "title": r.get("title", ""), "req_type": r.get("req_type"),
               "status": r.get("status"), "done": done(r), "estimate": r.get("estimate"), "assignee": r.get("assignee"),
               "iteration": r.get("iteration"), "parentId": r.get("parentId") if r.get("parentId") in work else None,
               "rank": r.get("rank"), "linked_requirements": links, "total_points": total, "done_points": finished,
               "children": kids}
        if kids:
            out["progress_pct"] = round(100 * finished / total, 1) if total else round(
                100 * sum(1 for k in kids if k["done"]) / len(kids), 1)
        return out

    return {"items": [node(r) for r in children.get(None, [])]}


@router.post("/backlog/{uid}/rank")
def rank(uid: str, body: dict[str, Any], store: Store = Depends(get_store)):
    """Move an item before or after a sibling (``{"before": uid}`` or ``{"after": uid}``). Ranks are renumbered
    10, 20, 30... within the parent, so the order is kept in the files and shows up in diffs."""
    uid = store.resolve_uid(uid) or uid
    item = store.get_requirement(uid)
    if item is None:
        raise not_found(uid)
    other_uid = store.resolve_uid(str(body.get("before") or body.get("after") or "")) or ""
    reqs = store.requirement_map()
    other = reqs.get(other_uid or "")
    if other is None:
        raise HTTPException(status_code=422, detail={"error": "bad_target", "message": "Say which item to move next to"})
    if (other.get("parentId") or None) != (item.get("parentId") or None):
        raise HTTPException(status_code=422, detail={"error": "different_parent",
                            "message": "Items can only be reordered next to an item with the same parent"})
    siblings = [r for r in reqs.values() if not r.get("deleted") and (r.get("parentId") or None) == (item.get("parentId") or None)
                and layout.family(r.get("req_type"), store.hierarchy) == "work" and r["uid"] != uid]
    siblings.sort(key=lambda r: (r.get("rank") if isinstance(r.get("rank"), (int, float)) else float("inf"), r.get("id") or ""))
    at = next(i for i, r in enumerate(siblings) if r["uid"] == other["uid"])
    siblings.insert(at if body.get("before") else at + 1, item)
    for i, r in enumerate(siblings):
        want = (i + 1) * 10
        if r.get("rank") != want:
            store.update_requirement(r["uid"], {"rank": want}, summary="Backlog order changed")
    return {"order": [r["uid"] for r in siblings]}
