"""
reqtool.routers.features
========================
Traceability, lifecycle, overview, roadmap, readiness, quality, query, test results, doctor, trend,
reviews, notifications and change sets (ENH-01..07, FEAT-01..12).
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from reqtool.actor import resolve_author
from reqtool.features import changesets, diff, doctor, insight, notifications, quality, query, reviews, snapshot
from reqtool.features import testresults, trend
from reqtool.intelligence import suggest_duplicates
from reqtool.store import Store
from .deps import get_store, not_found, publish_event, ReqUid

router = APIRouter()


def _bad(message: str, status: int = 422, error: str = "validation") -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, "message": message})


# --- traceability, lifecycle, overview, roadmap --------------------------------

@router.get("/requirements/{uid}/trace", tags=["traceability"])
def requirement_trace(uid: ReqUid, store: Store = Depends(get_store)):
    result = insight.requirement_trace(store, uid)
    if result is None:
        raise not_found(uid)
    return result


@router.get("/requirements/{uid}/lifecycle", tags=["traceability"])
def requirement_lifecycle(uid: ReqUid, store: Store = Depends(get_store)):
    result = insight.lifecycle(store, uid)
    if result is None:
        raise not_found(uid)
    return result


@router.get("/requirements/{uid}/summary", tags=["overview"])
def strategic_summary(uid: ReqUid, store: Store = Depends(get_store)):
    """Child counts by type and status, completion, estimate, open TBDs and validation for a Theme, Initiative or Epic."""
    result = insight.strategic_summary(store, uid)
    if result is None:
        raise not_found(uid)
    return result


@router.get("/overview", tags=["overview"])
def product_overview(product: Optional[str] = None, store: Store = Depends(get_store)):
    if product and product not in store.products:
        raise not_found(product)
    return insight.overview(store, product)


@router.get("/roadmap", tags=["overview"])
def get_roadmap(store: Store = Depends(get_store)):
    return insight.roadmap(store)


@router.post("/requirements/{uid}/impact-preview", tags=["traceability"])
def impact_preview(uid: ReqUid, body: dict[str, Any], store: Store = Depends(get_store)):
    """What an edit would affect, before it is saved."""
    result = insight.impact_preview(store, uid, body)
    if result is None:
        raise not_found(uid)
    return result


@router.get("/gate", tags=["validation"])
def release_gate(product: Optional[str] = None, store: Store = Depends(get_store)):
    """Release readiness: ``ready`` is false when any policy finding exists."""
    if product and product not in store.products:
        raise not_found(product)
    return insight.release_readiness(store, product)


# --- quality, query, duplicates -------------------------------------------------

@router.post("/quality/check", tags=["quality"])
def quality_check(body: dict[str, Any]):
    """Advisory findings for text as it is typed. Never blocks a save."""
    criteria = body.get("acceptance_criteria", 0)
    count = len(criteria) if isinstance(criteria, list) else int(criteria or 0)
    return {"findings": quality.check_text(str(body.get("title", "")), str(body.get("description", "")), count)}


@router.get("/requirements/{uid}/quality", tags=["quality"])
def requirement_quality(uid: ReqUid, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if req is None:
        raise not_found(uid)
    return {"uid": uid, "findings": quality.check_requirement(req)}


@router.get("/query", tags=["query"])
def run_query(q: str = "", store: Store = Depends(get_store)):
    """Search with the query language, for example ``status:approved type:safety no:verification``."""
    try:
        found = query.run(store.requirements, q)
    except query.QueryError as exc:
        raise _bad(str(exc))
    return {"query": q, "count": len(found), "results": [insight._ref(r) for r in found]}


@router.post("/duplicates/suggest", tags=["quality"])
def duplicate_suggestions(body: dict[str, Any], store: Store = Depends(get_store)):
    """Existing requirements similar to the text being authored."""
    return {"suggestions": suggest_duplicates(store, str(body.get("title", "")), str(body.get("description", "")),
                                              exclude_uid=body.get("exclude_uid"))}


# --- test results, doctor, trend ------------------------------------------------

@router.post("/test-results", tags=["verification"])
async def ingest_test_results(request: Request, source: str = "ci", run_url: str = "",
                              store: Store = Depends(get_store)):
    """Upload JUnit XML. Tests naming a requirement id set its verification status."""
    raw = await request.body()
    if len(raw) > 10 * 1024 * 1024:
        raise _bad("Result file is larger than 10 MB", 413, "too_large")
    try:
        result = testresults.ingest(store, raw.decode("utf-8", errors="replace"), source=source[:60], run_url=run_url[:300])
    except testresults.JUnitError as exc:
        raise _bad(str(exc))
    for item in result["updated"]:
        publish_event(store, "requirement_updated", {"uid": item["uid"], "id": item["id"]})
    return result


@router.get("/doctor", tags=["validation"])
def run_doctor(store: Store = Depends(get_store)):
    return doctor.run_doctor(store)


@router.get("/trend", tags=["baselines"])
def baseline_trend(store: Store = Depends(get_store)):
    return trend.trend(store)


@router.get("/baselines/field-diff", tags=["baselines"])
def baseline_field_diff(baseline_a: str, baseline_b: str = "HEAD", store: Store = Depends(get_store)):
    """Field-level difference per requirement between two baselines (or a baseline and HEAD)."""
    def ref(name: str) -> str:
        return name if name == "HEAD" or name.startswith("baseline/") else f"baseline/{name}"
    try:
        return diff.ref_diff(store.root, ref(baseline_a), ref(baseline_b))
    except ValueError as exc:
        raise not_found(str(exc))


@router.get("/snapshot.zip", tags=["exports"])
def stakeholder_snapshot(baseline: str = "", store: Store = Depends(get_store)):
    """The read-only stakeholder site for a baseline (or the current files) as a zip."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            snapshot.build_site(store, Path(tmp), baseline or None)
        except ValueError as exc:
            raise not_found(str(exc))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(Path(tmp).iterdir()):
                zf.write(f, f.name)
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="requirements-snapshot.zip"'})


# --- reviews and approvals --------------------------------------------------------

@router.post("/requirements/{uid}/review-requests", status_code=201, tags=["reviews"])
def request_review(uid: ReqUid, body: dict[str, Any], store: Store = Depends(get_store)):
    reviewers = body.get("reviewers")
    if not isinstance(reviewers, list) or not [r for r in reviewers if isinstance(r, str) and r.strip()]:
        raise _bad("reviewers must be a non-empty list of names")
    if store.get_requirement(uid) is None:
        raise not_found(uid)
    by = resolve_author(str(body.get("requested_by") or "reqtool"))
    created = reviews.request_review(store, uid, [r for r in reviewers if isinstance(r, str)], by)
    for row in created:
        publish_event(store, "review_requested", {"uid": uid, "id": store.requirements[uid].get("id"),
                                                  "reviewer": row["reviewer"], "by": by})
    return created


@router.get("/requirements/{uid}/review-requests", tags=["reviews"])
def list_review_requests(uid: ReqUid, store: Store = Depends(get_store)):
    if store.get_requirement(uid) is None:
        raise not_found(uid)
    return reviews.list_requests(store, uid=uid)


@router.get("/reviews", tags=["reviews"])
def review_inbox(reviewer: str, store: Store = Depends(get_store)):
    """Pending requests for one reviewer (stale ones are flagged)."""
    return [r for r in reviews.list_requests(store, reviewer=reviewer) if r["status"] in ("pending", "stale")]


@router.get("/requirements/{uid}/approvals", tags=["reviews"])
def requirement_approvals(uid: ReqUid, store: Store = Depends(get_store)):
    try:
        return reviews.approvals(store, uid)
    except KeyError:
        raise not_found(uid)


# --- notifications ----------------------------------------------------------------

@router.get("/notifications", tags=["notifications"])
def list_notifications(user: str, unread: bool = False, store: Store = Depends(get_store)):
    return notifications.inbox(store, user, unread_only=unread)


@router.post("/notifications/{item_id}/read", tags=["notifications"])
def read_notification(item_id: str, user: str, store: Store = Depends(get_store)):
    if not notifications.mark_read(store, user, item_id):
        raise not_found(item_id)
    return {"read": item_id}


@router.get("/notifications/preferences/{user}", tags=["notifications"])
def get_notification_prefs(user: str, store: Store = Depends(get_store)):
    return notifications.get_prefs(store, user)


@router.put("/notifications/preferences/{user}", tags=["notifications"])
def put_notification_prefs(user: str, body: dict[str, Any], store: Store = Depends(get_store)):
    events = body.get("events", list(notifications.NOTIFY_EVENTS))
    if not isinstance(events, list):
        raise _bad("events must be a list")
    try:
        return notifications.set_prefs(store, user, events, bool(body.get("muted", False)))
    except ValueError as exc:
        raise _bad(str(exc))


# --- change sets ------------------------------------------------------------------

def _changeset(fn, *args):
    try:
        return fn(*args)
    except changesets.ChangeSetError as exc:
        raise _bad(str(exc), 409, "conflict")


@router.get("/changesets", tags=["changesets"])
def list_changesets(store: Store = Depends(get_store)):
    return _changeset(changesets.listing, store)


@router.post("/changesets", status_code=201, tags=["changesets"])
def create_changeset(body: dict[str, Any], store: Store = Depends(get_store)):
    return _changeset(changesets.create, store, str(body.get("name", "")))


@router.get("/changesets/{name}/diff", tags=["changesets"])
def changeset_diff(name: str, store: Store = Depends(get_store)):
    return _changeset(changesets.diff, store, name)


@router.post("/changesets/{name}/merge", tags=["changesets"])
def merge_changeset(name: str, body: dict[str, Any], store: Store = Depends(get_store)):
    return _changeset(changesets.merge, store, name, str(body.get("reviewed_by", "")))


@router.post("/changesets/switch", tags=["changesets"])
def switch_changeset(body: dict[str, Any], store: Store = Depends(get_store)):
    return _changeset(changesets.switch, store, str(body.get("branch", "")))
