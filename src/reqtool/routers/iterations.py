"""
reqtool.routers.iterations
==========================
REST API router for Iteration, Sprint, Phase, and Milestone Management.
"""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from reqtool.store import Store
from reqtool.iterations import IterationStore
from reqtool.routers.deps import get_store

router = APIRouter(prefix="/iterations", tags=["iterations"])


@router.get("")
def list_iterations(store: Store = Depends(get_store)):
    it_store = IterationStore(store.root)
    return it_store.load_iterations()


@router.get("/{iteration_id}")
def get_iteration(iteration_id: str, store: Store = Depends(get_store)):
    it_store = IterationStore(store.root)
    it = it_store.get_iteration(iteration_id)
    if not it:
        raise HTTPException(status_code=404, detail=f"Iteration '{iteration_id}' not found")
    return it


@router.post("", status_code=201)
def create_or_update_iteration(body: dict[str, Any], store: Store = Depends(get_store)):
    it_store = IterationStore(store.root)
    try:
        return it_store.upsert_iteration(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{iteration_id}")
def delete_iteration(iteration_id: str, store: Store = Depends(get_store)):
    it_store = IterationStore(store.root)
    if it_store.delete_iteration(iteration_id):
        return {"deleted": iteration_id}
    raise HTTPException(status_code=404, detail=f"Iteration '{iteration_id}' not found")


@router.get("/{iteration_id}/metrics")
def iteration_metrics(iteration_id: str, store: Store = Depends(get_store)):
    it_store = IterationStore(store.root)
    it = it_store.get_iteration(iteration_id)
    if not it:
        raise HTTPException(status_code=404, detail=f"Iteration '{iteration_id}' not found")

    # Calculate assigned requirements and burndown metrics
    # Requirements record their sprint in `iteration`, which holds the iteration's id (or its title).
    names = {iteration_id, it.get("title")} - {None, ""}
    reqs = [r for r in store.requirements.values() if not r.get("deleted") and r.get("iteration") in names]
    total_assigned = len(reqs)
    approved_count = len([r for r in reqs if r.get("status") == "approved"])
    draft_count = len([r for r in reqs if r.get("status") == "draft"])
    in_review_count = len([r for r in reqs if r.get("status") in ("review", "in_review")])

    completion_pct = round((approved_count / total_assigned * 100)) if total_assigned > 0 else 0

    return {
        "iteration_id": iteration_id,
        "title": it.get("title"),
        "methodology": it.get("methodology"),
        "total_requirements": total_assigned,
        "approved": approved_count,
        "draft": draft_count,
        "in_review": in_review_count,
        "completion_percentage": completion_pct,
        "capacity_story_points": it.get("capacity_story_points", 0),
        "status": it.get("status"),
    }
