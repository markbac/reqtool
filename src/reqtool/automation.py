"""
reqtool.automation
==================
Workflow Automation Engine for Rule Triggers and Downstream Actions.
Supports event-driven automation rules stored in .reqtool/automation_rules.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from reqtool.fileio import load_yaml, save_yaml, utcnow_iso
from reqtool.store import Store


class AutomationEngine:
    def __init__(self, root: Path):
        self.root = root
        self.rules_file = root / ".reqtool" / "automation_rules.yaml"

    def load_rules(self) -> list[dict[str, Any]]:
        if not self.rules_file.exists():
            self._seed_default_rules()
        data = load_yaml(self.rules_file)
        if isinstance(data, list):
            return data
        return []

    def save_rules(self, rules: list[dict[str, Any]]) -> None:
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.rules_file, rules)

    def _seed_default_rules(self) -> None:
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
        self.save_rules(defaults)

    def execute_event_rules(self, store: Store, event_name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Evaluate and execute automation actions matching an event."""
        executed = []
        rules = self.load_rules()
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
                if uid and action == "set_field":
                    field = rule.get("target_field")
                    val = rule.get("target_value")
                    if field and val:
                        req = store.get_requirement(uid)
                        if req:
                            store.update_requirement(uid, {field: val}, summary=f"Automation rule '{rule.get('name')}' executed")
                            executed.append({"rule_id": rule.get("id"), "action": action, "uid": uid})
        return executed
