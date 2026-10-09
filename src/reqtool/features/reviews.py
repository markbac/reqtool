"""
reqtool.features.reviews
========================
Review requests bound to a content hash (FEAT-04). Stored in ``.reqtool/reviews.yaml`` so they never
alter the requirement's own hash. A request goes stale when the content changes after it was made.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from reqtool.fileio import load_yaml, save_yaml, utcnow_iso


def _path(store):
    return store.root / ".reqtool" / "reviews.yaml"


def _load(store) -> list[dict[str, Any]]:
    path = _path(store)
    if not path.exists():
        return []
    try:
        return list(load_yaml(path).get("requests", []))
    except Exception:
        return []


def _save(store, rows: list[dict[str, Any]]) -> None:
    save_yaml(_path(store), {"requests": rows})


def _view(row: dict, req: Optional[dict]) -> dict:
    stale = row["status"] == "pending" and req is not None and req.get("content_hash") != row["content_hash"]
    return {**row, "status": "stale" if stale else row["status"]}


def request_review(store, uid: str, reviewers: list[str], requested_by: str) -> list[dict[str, Any]]:
    req = store.get_requirement(uid)
    if req is None:
        raise KeyError(uid)
    with store.lock:
        rows = _load(store)
        created = []
        for reviewer in dict.fromkeys(r.strip() for r in reviewers if r and r.strip()):
            # a fresh request replaces an older pending one for the same person
            rows = [r for r in rows if not (r["uid"] == uid and r["reviewer"] == reviewer and r["status"] == "pending")]
            row = {"id": uuid.uuid4().hex[:12], "uid": uid, "reviewer": reviewer, "requested_by": requested_by,
                   "requested_at": utcnow_iso(), "content_hash": req.get("content_hash", ""),
                   "version": req.get("version", ""), "status": "pending"}
            rows.append(row)
            created.append(row)
        _save(store, rows)
    return created


def list_requests(store, uid: Optional[str] = None, reviewer: Optional[str] = None) -> list[dict[str, Any]]:
    rows = [r for r in _load(store) if (uid is None or r["uid"] == uid) and (reviewer is None or r["reviewer"] == reviewer)]
    return [_view(r, store.requirements.get(r["uid"])) for r in rows]


def record_approval(store, uid: str, approver: str) -> None:
    """Mark the approver's pending request for this uid as approved."""
    with store.lock:
        rows = _load(store)
        changed = False
        for r in rows:
            if r["uid"] == uid and r["reviewer"] == approver and r["status"] == "pending":
                r["status"], r["completed_at"] = "approved", utcnow_iso()
                changed = True
        if changed:
            _save(store, rows)


def approvals(store, uid: str) -> dict[str, Any]:
    """Who approved which version: the signed approval plus earlier ones from the history."""
    req = store.get_requirement(uid)
    if req is None:
        raise KeyError(uid)
    out = []
    for entry in req.get("history") or []:
        summary = entry.get("summary", "")
        if summary.startswith("Approved by "):
            out.append({"approved_by": summary[len("Approved by "):], "version": entry.get("version"),
                        "date": entry.get("date") or entry.get("timestamp")})
    current = req.get("approval") or {}
    return {"approvals": out, "current": {k: current.get(k) for k in
            ("status", "approved_by", "approved_date", "signed_version", "signed_hash", "identity_verified")},
            "current_hash": req.get("content_hash")}
