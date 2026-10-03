"""
reqtool.stores.hierarchy_store
==============================
Hierarchy and workflow management helper functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from reqtool.fileio import load_yaml
from reqtool.models import (
    HierarchyConfig, ItemTypeConfig, HierarchyRule,
    HierarchyWorkflowDef, WorkflowGuard, CrossLayerRule, RelationshipTypeDef,
)

log = logging.getLogger(__name__)


def load_hierarchy(repo_root: Path) -> HierarchyConfig:
    project_path = repo_root / ".reqtool" / "hierarchy.yaml"
    default_path = Path(__file__).parent.parent / "defaults" / "hierarchy.yaml"
    for path in (project_path, default_path):
        if path.exists():
            try:
                data = load_yaml(path)
                if isinstance(data, dict):
                    return parse_hierarchy(data)
            except Exception as exc:
                log.warning("Failed to load hierarchy from %s: %s", path, exc)
    return HierarchyConfig()


def parse_hierarchy(data: dict) -> HierarchyConfig:
    types = {
        k: ItemTypeConfig.model_validate(v)
        for k, v in (data.get("types") or {}).items()
    }
    hierarchy = {
        k: HierarchyRule.model_validate(v)
        for k, v in (data.get("hierarchy") or {}).items()
    }
    workflows: dict[str, HierarchyWorkflowDef] = {}
    for wf_id, wf_data in (data.get("workflows") or {}).items():
        guards_raw = wf_data.get("guards") or {}
        guards = {
            state: WorkflowGuard.model_validate(g)
            for state, g in guards_raw.items()
        }
        workflows[wf_id] = HierarchyWorkflowDef(
            states=wf_data.get("states", []),
            transitions=wf_data.get("transitions", {}),
            initial=wf_data.get("initial", "draft"),
            guards=guards,
        )
    cross_layer_rules = [
        CrossLayerRule.model_validate(r)
        for r in (data.get("cross_layer_rules") or [])
    ]
    default_rel_types = [
        RelationshipTypeDef.model_validate(r)
        for r in (data.get("default_relationship_types") or [])
    ]
    enforce = str(data.get("enforce", "warn")).lower()
    if enforce not in ENFORCE_MODES:
        log.warning("Unknown hierarchy.enforce '%s'; using 'warn'", enforce)
        enforce = "warn"
    return HierarchyConfig(
        enforce=enforce,
        types=types,
        hierarchy=hierarchy,
        workflows=workflows,
        dor=data.get("dor", {}),
        dod=data.get("dod", {}),
        cross_layer_rules=cross_layer_rules,
        default_relationship_types=default_rel_types,
    )


def get_workflow_for_type(hierarchy: HierarchyConfig, req_type: str) -> Optional[HierarchyWorkflowDef]:
    type_cfg = hierarchy.types.get(req_type)
    if not type_cfg:
        return None
    return hierarchy.workflows.get(type_cfg.workflow)


ENFORCE_MODES = ("off", "warn", "error")


def check_parent_type(hierarchy: HierarchyConfig, parent_type: str, child_type: str) -> Optional[str]:
    """Return a message if ``child_type`` may not sit under ``parent_type``, else None.

    A parent type with no rule in the hierarchy is unconstrained.
    """
    rule = hierarchy.hierarchy.get(parent_type)
    if rule is None or child_type in rule.allowed_children:
        return None
    allowed = ", ".join(rule.allowed_children) or "none"
    return f"A '{child_type}' cannot be a child of a '{parent_type}' (allowed: {allowed})"


# Relationship types that are never constrained by cross_layer_rules.
UNCONSTRAINED_REL_TYPES = ("relates_to", "depended_by")


def check_relationship(hierarchy: HierarchyConfig, source_type: str, target_type: str,
                       rel_type: str) -> Optional[str]:
    """Return a message if ``rel_type`` may not link ``source_type`` to ``target_type``.

    A type pair is governed when some rule covers it in either direction; pairs
    no rule mentions are unconstrained. Within a governed pair only the rel types
    listed for that exact direction are allowed.
    """
    if rel_type in UNCONSTRAINED_REL_TYPES:
        return None
    governed = False
    for rule in hierarchy.cross_layer_rules:
        fwd = source_type in rule.source_types and target_type in rule.target_types
        rev = target_type in rule.source_types and source_type in rule.target_types
        if fwd:
            if rel_type in rule.allowed_rel_types:
                return None
            governed = True
        elif rev:
            governed = True
    if not governed:
        return None
    return (f"'{rel_type}' is not allowed from a '{source_type}' to a '{target_type}' "
            f"(see cross_layer_rules in hierarchy.yaml)")


def get_allowed_children(hierarchy: HierarchyConfig, req_type: str) -> list[str]:
    rule = hierarchy.hierarchy.get(req_type)
    if rule is None:
        return []
    return rule.allowed_children


def check_transition_guard(
    hierarchy: HierarchyConfig,
    req: dict[str, Any],
    to_state: str,
) -> Optional[str]:
    req_type = req.get("req_type", "functional")
    wf = get_workflow_for_type(hierarchy, req_type)
    if not wf:
        return None
    guard = wf.guards.get(to_state)
    if not guard:
        return None

    for field_path in guard.requires_fields:
        parts = field_path.split(".")
        val = req
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = None
                break
        if not val:
            return guard.message or f"Field '{field_path}' is required before transitioning to '{to_state}'."

    if guard.requires_ac and not req.get("acceptance_criteria"):
        return guard.message or f"At least one acceptance criterion is required before transitioning to '{to_state}'."

    return None


def validate_transition(
    hierarchy: HierarchyConfig,
    fallback_workflow: Any,
    req: dict[str, Any],
    to_state: str,
) -> Optional[str]:
    req_type = req.get("req_type", "functional")
    current = req.get("status", "draft")
    wf = get_workflow_for_type(hierarchy, req_type)
    if not wf:
        allowed = fallback_workflow.transitions.get(current, [])
        if to_state not in allowed and to_state != current:
            return f"Transition from '{current}' to '{to_state}' is not permitted."
        return None
    allowed = wf.transitions.get(current, [])
    if to_state not in allowed and to_state != current:
        return f"Transition from '{current}' to '{to_state}' is not permitted for type '{req_type}'."
    return check_transition_guard(hierarchy, req, to_state)


def next_id_for_type(hierarchy: HierarchyConfig, requirements: dict[str, dict[str, Any]], req_type: str) -> str:
    type_cfg = hierarchy.types.get(req_type)
    prefix = type_cfg.id_prefix if type_cfg else req_type.upper()[:3]

    max_n = 0
    for req in requirements.values():
        rid = req.get("id", "")
        if rid.startswith(prefix + "-"):
            try:
                n = int(rid[len(prefix) + 1:])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return f"{prefix}-{max_n + 1:03d}"


def default_checklist(hierarchy: HierarchyConfig, kind: str, req_type: str) -> list[dict[str, Any]]:
    templates = hierarchy.dor if kind == "dor" else hierarchy.dod
    items = templates.get(req_type, [])
    return [{"item": i.get("item", ""), "checked": False} for i in items]
