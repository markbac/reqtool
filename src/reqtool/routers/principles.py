"""
reqtool.routers.principles
==========================
FastAPI router for principle endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends

from reqtool.principles import with_placement
from reqtool.services.principles import PrincipleService
from reqtool.store import Store

from reqtool.models import CommitRequest, CreatePrincipleRequest, UpdatePrincipleRequest
from .deps import get_store, not_found, commit_artefact

log = logging.getLogger(__name__)

router = APIRouter(tags=["principles"])


def get_service(store: Store = Depends(get_store)) -> PrincipleService:
    return PrincipleService(store)


@router.get("/principles")
def list_principles(area: Optional[str] = None, category: Optional[str] = None, status: Optional[str] = None,
                    q: Optional[str] = None, service: PrincipleService = Depends(get_service)):
    """Live principles, optionally narrowed by area, category, status or a search on id and title."""
    return service.list(area, category, status, q)


@router.get("/principles/areas")
def principle_areas(service: PrincipleService = Depends(get_service)):
    """Areas and categories with counts (the vocabulary in order, then anything in use it does not list)."""
    return service.areas()


@router.get("/principles/vocabulary")
def principle_vocabulary(service: PrincipleService = Depends(get_service)):
    return service.vocabulary()


@router.put("/principles/vocabulary")
def set_principle_vocabulary(body: dict[str, Any], service: PrincipleService = Depends(get_service)):
    """Replace the repository's areas and categories (administrators)."""
    return service.set_vocabulary(body.get("vocabulary") or {})


@router.get("/principles/packs")
def principle_packs(service: PrincipleService = Depends(get_service)):
    """The default packs, one per area, with how many of their principles the repository already has."""
    return service.packs()


@router.post("/principles/packs/{area}")
def add_principle_pack(area: str, service: PrincipleService = Depends(get_service)):
    """Add a pack's principles to the repository without duplicating ids (administrators)."""
    return service.add_pack(area)


@router.get("/principles/{uid}")
def get_principle(uid: str, store: Store = Depends(get_store)):
    p = store.get_principle(uid)
    if p is None:
        raise not_found(uid)
    return with_placement(p)


@router.post("/principles", status_code=201)
def create_principle(body: CreatePrincipleRequest, store: Store = Depends(get_store)):
    return store.create_principle(body.model_dump(exclude_none=True))


@router.put("/principles/{uid}")
def update_principle(uid: str, body: UpdatePrincipleRequest, store: Store = Depends(get_store)):
    result = store.update_principle(uid, body.model_dump(exclude_none=True), summary="Updated via API")
    if result is None:
        raise not_found(uid)
    return result


@router.delete("/principles/{uid}")
def delete_principle(uid: str, store: Store = Depends(get_store)):
    result = store.delete_principle(uid)
    if result is None:
        raise not_found(uid)
    return result


@router.post("/principles/{uid}/commit")
def commit_principle(uid: str, body: CommitRequest, store: Store = Depends(get_store)):
    p = store.get_principle(uid)
    if p is None:
        raise not_found(uid)
    return commit_artefact(
        store, body, store.principle_path(uid),
        bump=lambda message: store.update_principle(
            uid, {}, increment=body.increment or "patch", summary=message, change_ref=body.change_ref),
        undo=lambda: store.restore_principle(uid, p),
        version=lambda: (store.get_principle(uid) or {}).get("version", ""))