"""
reqtool.routers.visuals
=======================
Read-only views of the work: hierarchy, coverage, impact, flow, burn-up, decision ageing, principle heatmap,
the traceability grid and the roadmap board. The data is assembled in ``reqtool.features.visuals``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from reqtool.features import visuals
from reqtool.store import Store
from .deps import get_store, not_found

router = APIRouter(tags=["views"])


def _split(value: Optional[str]) -> Optional[list[str]]:
    items = [v.strip() for v in (value or "").split(",") if v.strip()]
    return items or None


@router.get("/views/hierarchy")
def view_hierarchy(product: Optional[str] = None, types: Optional[str] = Query(None, description="Comma-separated types"),
                   statuses: Optional[str] = Query(None, description="Comma-separated statuses"),
                   branch: Optional[str] = None, limit: int = Query(visuals.NODE_CAP, ge=1, le=5000),
                   store: Store = Depends(get_store)):
    """Items in tree order with their parents. Filters keep the ancestors of every match."""
    return visuals.hierarchy_tree(store, product, _split(types), _split(statuses), branch, limit)


@router.get("/views/type-structure")
def view_type_structure(store: Store = Depends(get_store)):
    """Which item type may sit under which, as Mermaid text."""
    return visuals.type_structure_mermaid(store)


@router.get("/views/coverage")
def view_coverage(by: str = "status", product: Optional[str] = None, store: Store = Depends(get_store)):
    """Counts per status (or verification state) at every level of the hierarchy."""
    return visuals.coverage_tree(store, by, product)


@router.get("/views/impact/{uid}")
def view_impact(uid: str, depth: int = Query(2, ge=1, le=3), types: Optional[str] = None,
                store: Store = Depends(get_store)):
    """Everything within a few hops of one item, nearest first, capped for legibility."""
    graph = visuals.impact_graph(store, store.resolve_uid(uid) or uid, depth, _split(types))
    if graph is None:
        raise not_found(uid)
    return graph


@router.get("/views/flow")
def view_flow(stuck_days: Optional[int] = Query(None, ge=1, le=3650), req_type: Optional[str] = None,
              store: Store = Depends(get_store)):
    """Items per workflow state, how long they have sat there, and which are stuck."""
    return visuals.flow(store, stuck_days, req_type)


@router.get("/views/burnup/{iteration_id}")
def view_burnup(iteration_id: str, store: Store = Depends(get_store)):
    """Scope against done over time for one iteration."""
    data = visuals.burnup(store, iteration_id)
    if data is None:
        raise not_found(iteration_id)
    return data


@router.get("/views/decisions")
def view_decision_ageing(store: Store = Depends(get_store)):
    """Open decisions and questions, oldest first, with what each blocks."""
    return visuals.decision_ageing(store)


@router.get("/views/principles")
def view_principle_heatmap(store: Store = Depends(get_store)):
    """Principle area and category against how many requirements cite them."""
    return visuals.principle_heatmap(store)


@router.get("/views/principles/{uid}/citations")
def view_principle_citations(uid: str, store: Store = Depends(get_store)):
    """The requirements that cite one principle."""
    found = store.principle_map().get(uid) or next(
        (p for p in store.principle_map().values() if p.get("id") == uid), None)
    if found is None:
        raise not_found(uid)
    return visuals.principle_citations(store, found["uid"])


@router.get("/traceability/grid")
def traceability_grid(columns: str = "tests", product: Optional[str] = None, req_type: Optional[str] = None,
                      status: Optional[str] = None, gaps: bool = False, offset: int = Query(0, ge=0),
                      limit: int = Query(100, ge=1, le=1000), format: str = Query("json", pattern="^(json|csv)$"),
                      store: Store = Depends(get_store)):
    """Requirements against tests, modules or decisions. ``gaps=true`` keeps rows with no link; ``format=csv`` downloads."""
    grid = visuals.trace_grid(store, columns, product, req_type, status, gaps, offset, limit)
    if format == "csv":
        return Response(visuals.trace_grid_csv(grid), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="traceability-grid.csv"'})
    return grid


@router.get("/roadmap/board")
def roadmap_board(group_by: str = Query("release", pattern="^(release|iteration)$"), store: Store = Depends(get_store)):
    """Themes as lanes, releases or iterations as columns, with dependency links and the longest chain."""
    return visuals.roadmap_board(store, group_by)
