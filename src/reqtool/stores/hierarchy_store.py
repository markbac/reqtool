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
    HierarchyWorkflowDef, WorkflowGuard, CrossLayerRule, RelationshipTypeDef, RulesConfig, FlowConfig,
)

log = logging.getLogger(__name__)


def default_hierarchy_data() -> dict:
    """The hierarchy file shipped with reqtool, as plain data."""
    data = load_yaml(Path(__file__).parent.parent / "defaults" / "hierarchy.yaml")
    return data if isinstance(data, dict) else {}


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
        type_fields=data.get("type_fields") or {},
        cross_layer_rules=cross_layer_rules,
        default_relationship_types=default_rel_types,
        rules=RulesConfig.model_validate(data.get("rules") or {}),
        flow=FlowConfig.model_validate(data.get("flow") or {}),
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


def open_children(
    hierarchy: HierarchyConfig,
    requirements: dict[str, dict[str, Any]],
    req: dict[str, Any],
    state: str,
) -> list[str]:
    """Ids of live direct children not in a state the guard for ``state`` allows (empty if no such guard)."""
    wf = get_workflow_for_type(hierarchy, req.get("req_type", "functional"))
    guard = wf.guards.get(state) if wf else None
    if not guard or not guard.requires_children_in or guard.children_enforce == "off":
        return []
    uid = req.get("uid")
    return sorted(
        c.get("id", c_uid) for c_uid, c in requirements.items()
        if not c.get("deleted") and c.get("parentId") == uid and uid
        and c.get("status") not in guard.requires_children_in)


def check_transition_guard(
    hierarchy: HierarchyConfig,
    req: dict[str, Any],
    to_state: str,
    requirements: Optional[dict[str, dict[str, Any]]] = None,
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

    if requirements is not None and guard.children_enforce == "error":
        blocking = open_children(hierarchy, requirements, req, to_state)
        if blocking:
            return (f"Cannot move to '{to_state}' while child items are not in "
                    f"{'/'.join(guard.requires_children_in)}: {', '.join(blocking)}")

    return None


def _field_value(req: dict[str, Any], path: str) -> Any:
    val: Any = req
    for part in path.split("."):
        val = val.get(part) if isinstance(val, dict) else None
    return val


def transition_options(
    hierarchy: HierarchyConfig,
    fallback_workflow: Any,
    req: dict[str, Any],
    requirements: Optional[dict[str, dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Every state ``req`` may move to, with what entering it needs and whether that is met now.

    ``requires.fields`` lists each required field with whether it is filled, so a UI can ask for just the gaps.
    """
    from reqtool.workflows import field_label
    req_type = req.get("req_type", "functional")
    current = req.get("status", "draft")
    wf = get_workflow_for_type(hierarchy, req_type)
    if wf:
        states = {s.id: s for s in wf.states}
        targets = wf.transitions.get(current, [])
    else:
        states = {s.id: s for s in fallback_workflow.states}
        targets = fallback_workflow.transitions.get(current, [])
    options = []
    for to in targets:
        state = states.get(to)
        guard = wf.guards.get(to) if wf else None
        fields = [{"path": f, "label": field_label(f), "filled": bool(_field_value(req, f))}
                  for f in (guard.requires_fields if guard else [])]
        children = open_children(hierarchy, requirements, req, to) if requirements is not None and guard else []
        problem = check_transition_guard(hierarchy, req, to, requirements)
        options.append({
            "to": to,
            "label": state.label if state else to,
            "colour": state.colour if state else DEFAULT_STATE_COLOUR,
            "terminal": bool(state.terminal) if state else False,
            "problem": problem,
            "requires": {
                "fields": fields,
                "acceptance_criteria": bool(guard and guard.requires_ac),
                "has_acceptance_criteria": bool(req.get("acceptance_criteria")),
                "children_in": list(guard.requires_children_in) if guard else [],
                "children_enforce": guard.children_enforce if guard else "off",
                "open_children": children,
                "message": guard.message if guard else "",
            },
        })
    return options


DEFAULT_STATE_COLOUR = "#8b949e"


def validate_transition(
    hierarchy: HierarchyConfig,
    fallback_workflow: Any,
    req: dict[str, Any],
    to_state: str,
    requirements: Optional[dict[str, dict[str, Any]]] = None,
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
    return check_transition_guard(hierarchy, req, to_state, requirements)


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
    return [{"item": i.get("item", ""), "checked": False, **({"advisory": True} if i.get("advisory") else {})}
            for i in items]
