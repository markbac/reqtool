"""
reqtool.routers.analysis
========================
FastAPI router for validation endpoints.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends

from reqtool.store import Store
from reqtool.validation import validate_all, validate_single
from .deps import get_store

log = logging.getLogger(__name__)

router = APIRouter(tags=["validation"])


@router.get("/validate")
def run_validation(store: Store = Depends(get_store)):
    return validate_all(store)


@router.get("/validate/{uid}")
def validate_artefact(uid: str, store: Store = Depends(get_store)):
    return validate_single(store, uid)
