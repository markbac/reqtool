"""
reqtool.automation
==================
Workflow Automation Engine for Rule Triggers and Downstream Actions.
Supports event-driven automation rules stored in .reqtool/automation_rules.yaml.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from reqtool.fileio import load_yaml, save_yaml
from reqtool.store import Store

log = logging.getLogger(__name__)

# The one rule schema: what the engine runs, the API validates and the UI edits.
EVENTS: dict[str, str] = {
    "requirement_created": "Requirement created",
    "requirement_updated": "Requirement updated",
    "requirement_approved": "Requirement approved",
    "status_changed": "Status changed",
}
# action id -> (label, fields it requires)
ACTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "set_field": ("Set field", ("target_field", "target_value")),
    "add_tag": ("Add tag", ("target_value",)),
}


class AutomationRule(BaseModel):
    """One automation rule. ``condition`` keys must equal the event payload's values."""
    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = None
    name: str = Field(min_length=1)
    enabled: bool = True
    event: str
    condition: dict[str, Any] = Field(default_factory=dict)
    action: str
    target_field: Optional[str] = None
    target_value: Optional[str] = None

    @field_validator("event")
    @classmethod
    def _known_event(cls, v: str) -> str:
        if v not in EVENTS:
            raise ValueError(f"unknown event '{v}'; use one of: {', '.join(EVENTS)}")
        return v

    @field_validator("action")
    @classmethod
    def _known_action(cls, v: str) -> str:
        if v not in ACTIONS:
            raise ValueError(f"unknown action '{v}'; use one of: {', '.join(ACTIONS)}")
        return v

    @model_validator(mode="after")
    def _action_fields(self):
        for field in ACTIONS[self.action][1]:
            if not getattr(self, field):
                raise ValueError(f"action '{self.action}' requires {field}")
        return self


class AutomationEngine:
    def __init__(self, root: Path):
        self.root = root
        self.rules_file = root / ".reqtool" / "automation_rules.yaml"

    def load_rules(self, include_defaults: bool = True) -> list[dict[str, Any]]:
        if not self.rules_file.exists():
            # Example rules are shown from memory until the first explicit save; they never run before that.
            return self._default_rules() if include_defaults else []
        data = load_yaml(self.rules_file)
        if isinstance(data, list):
            return data
        return []

    def save_rules(self, rules: list[dict[str, Any]]) -> None:
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.rules_file, rules)

    @staticmethod
    def _default_rules() -> list[dict[str, Any]]:
        defaults = [
            {
                "id": "rule-auto-assign-qa",
                "name": "Auto-assign QA on Approval",
                "event": "requirement_approved",
                "condition": {"status": "approved"},
                "action": "set_field",
                "target_field": "assignee",
                "target_value": "qa_lead",
                "enabled": True,
            },
            {
                "id": "rule-auto-tag-safety",
                "name": "Auto-tag Safety Critical Items",
                "event": "requirement_created",
                "condition": {"req_type": "safety"},
                "action": "add_tag",
                "target_value": "ASIL-D",
                "enabled": True,
            },
        ]
        return defaults

    def execute_event_rules(self, store: Store, event_name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Evaluate and execute automation actions matching an event."""
        executed = []
        rules = self.load_rules(include_defaults=False)
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("event") != event_name:
                continue

            cond = rule.get("condition", {})
            match = True
            for k, v in cond.items():
                if payload.get(k) != v:
                    match = False
                    break

            if match:
                action = rule.get("action")
                uid = payload.get("uid")
                req = store.get_requirement(uid) if uid else None
                if not req:
                    continue
                summary = f"Automation rule '{rule.get('name')}' executed"
                val = rule.get("target_value")
                if action == "set_field" and rule.get("target_field") and val:
                    if req.get(rule["target_field"]) != val:  # idempotent
                        store.update_requirement(uid, {rule["target_field"]: val}, summary=summary)
                        executed.append({"rule_id": rule.get("id"), "action": action, "uid": uid})
                elif action == "add_tag" and val:
                    tags = list(req.get("tags") or [])
                    if val not in tags:  # idempotent
                        store.update_requirement(uid, {"tags": tags + [val]}, summary=summary)
                        executed.append({"rule_id": rule.get("id"), "action": action, "uid": uid})
        return executed


def automation_subscriber(store: Store, event: str, payload: dict[str, Any]) -> None:
    """EventPublisher subscriber: run matching rules for a published event.

    Conditions are matched against the event payload plus the requirement's current
    fields. Rule actions write through the store directly and do not publish events,
    so rules cannot trigger each other.
    """
    if event not in EVENTS:
        return
    uid = payload.get("uid")
    req = store.get_requirement(uid) if uid else None
    context = {**(req or {}), **payload}
    for done in AutomationEngine(store.root).execute_event_rules(store, event, context):
        log.info("Automation rule %s ran %s on %s (event %s)", done["rule_id"], done["action"], done["uid"], event)
