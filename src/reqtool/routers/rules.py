"""
reqtool.routers.rules
=====================
Parent and child rules: the rule set kept in ``.reqtool/hierarchy.yaml``, a preview of what a move would trigger,
and the report of moves that were forced past a rule. Changing the rules is for administrators.
"""

from __future__ import annotations

import copy
from functools import partial
from typing import Any

from fastapi import APIRouter, Depends

from reqtool import workflow_rules as rules
from reqtool.models import RulesConfig
from reqtool.services.errors import Invalid
from reqtool.services.requirements import RequirementService
from reqtool.store import Store
from .deps import get_store, publish_event

router = APIRouter(tags=["rules"])


def _service(store: Store) -> RequirementService:
    return RequirementService(store, partial(publish_event, store))


def _describe(store: Store) -> dict[str, Any]:
    cfg = store.hierarchy.rules
    return {**cfg.model_dump(), "problems": rules.check_config(store.hierarchy),
            "kinds": {"checks": list(rules.CHECK_KINDS), "changes": list(rules.CHANGE_KINDS)},
            "modes": {"checks": list(rules.CHECK_MODES), "changes": list(rules.CHANGE_MODES)},
            "scopes": {k: list(v) for k, v in rules.SCOPES.items()},
            "tokens": ["@initial", "@started", "@terminal", "@done", "@cancelled"]}


@router.get("/rules")
def get_rules(store: Store = Depends(get_store)):
    """The parent and child rules, with problems found in them (missing types or states, bad modes)."""
    return _describe(store)


@router.put("/rules")
def put_rules(body: dict, store: Store = Depends(get_store)):
    """Replace the rule set. Refused when a rule is malformed; a rule naming an unknown type or state is refused too."""
    try:
        cfg = RulesConfig.model_validate({"override": body.get("override", "editor"), "rules": body.get("rules") or []})
    except Exception as exc:
        raise Invalid(f"Invalid rules: {exc}") from exc
    trial = store.hierarchy.model_copy(update={"rules": cfg})
    problems = rules.check_config(trial)
    if problems:
        raise Invalid("; ".join(problems), errors=problems)
    with store.lock:
        data = copy.deepcopy(store.hierarchy_data())
        data["rules"] = cfg.model_dump(exclude_defaults=False)
        store.write_hierarchy(data)
    return _describe(store)


@router.post("/rules/preview")
def preview_rules(body: dict, store: Store = Depends(get_store)):
    """Dry run: the checks and roll-ups that moving ``uid`` to ``to_state`` would trigger. Changes nothing."""
    service = _service(store)
    key = body.get("uid", "")
    if not key or not body.get("to_state"):
        raise Invalid("uid and to_state are required")
    return service.rule_preview(store.resolve_uid(key) or key, body["to_state"])


@router.get("/rules/overrides")
def list_overrides(store: Store = Depends(get_store)):
    """Items whose current status was reached by forcing a move past a rule, with who, why and when."""
    return {"overrides": _service(store).overrides()}
