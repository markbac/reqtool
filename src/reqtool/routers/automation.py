"""
reqtool.routers.automation
==========================
REST API router for Automation Rules Management.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from reqtool.store import Store
from reqtool.automation import AutomationEngine, AutomationRule, EVENTS, ACTIONS
from reqtool.routers.deps import get_store

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/schema")
def rule_schema():
    """Supported events and actions for building rules."""
    return {
        "events": [{"id": k, "label": v} for k, v in EVENTS.items()],
        "actions": [{"id": k, "label": label, "requires": list(req)} for k, (label, req) in ACTIONS.items()],
    }


@router.get("/rules")
def list_rules(store: Store = Depends(get_store)):
    engine = AutomationEngine(store.root)
    return engine.load_rules()


@router.put("/rules")
def save_rules(rules: list[AutomationRule], store: Store = Depends(get_store)):
    """Replace all rules. Invalid rules return 422 with the failing rule's index in ``loc``."""
    ids = [r.id for r in rules if r.id]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "Rule ids must be unique"})
    out = []
    for rule in rules:
        data = rule.model_dump(exclude_none=True)
        data.setdefault("id", f"rule-{uuid.uuid4().hex[:8]}")
        out.append(data)
    AutomationEngine(store.root).save_rules(out)
    return {"saved": len(out)}
