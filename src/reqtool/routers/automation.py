"""
reqtool.routers.automation
==========================
REST API router for Automation Rules Management.
"""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from reqtool.store import Store
from reqtool.automation import AutomationEngine
from reqtool.routers.deps import get_store

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/rules")
def list_rules(store: Store = Depends(get_store)):
    engine = AutomationEngine(store.root)
    return engine.load_rules()


@router.put("/rules")
def save_rules(rules: list[dict[str, Any]], store: Store = Depends(get_store)):
    engine = AutomationEngine(store.root)
    engine.save_rules(rules)
    return {"saved": len(rules)}
