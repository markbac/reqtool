"""Workflow administration: list, validate, save, create, delete and assign workflows.

Workflows are stored in the repository's ``.reqtool/hierarchy.yaml`` (copied there from the bundled defaults
when the repository is created), so each project owns and can change its own.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

from reqtool import workflows as wf_lib
from reqtool.store import Store
from .errors import Conflict, Invalid, MissingItem

NEW_WORKFLOW = {
    "initial": "draft",
    "states": [
        {"id": "draft", "label": "Draft", "colour": "#8b949e", "terminal": False},
        {"id": "active", "label": "Active", "colour": "#1f6feb", "terminal": False},
        {"id": "done", "label": "Done", "colour": "#238636", "terminal": True},
    ],
    "transitions": {"draft": ["active"], "active": ["done", "draft"], "done": []},
}


class WorkflowService:
    def __init__(self, store: Store) -> None:
        self.store = store

    # -- reading -----------------------------------------------------------------------------

    def _definitions(self) -> dict[str, dict[str, Any]]:
        return {wid: wf_lib.normalise(wf.model_dump()) for wid, wf in self.store.hierarchy.workflows.items()}

    def _used_by(self, workflow_id: str) -> list[str]:
        return sorted(t for t, cfg in self.store.hierarchy.types.items() if cfg.workflow == workflow_id)

    def _stranded(self, workflow_id: str, definition: Mapping[str, Any]) -> list[str]:
        """Warnings for live items whose status is not a state of ``definition``."""
        states = {s["id"] for s in definition["states"]}
        types = set(self._used_by(workflow_id))
        counts: dict[str, int] = {}
        for req in self.store.live_requirements():
            if req.get("req_type") in types and req.get("status") not in states:
                counts[req.get("status", "")] = counts.get(req.get("status", ""), 0) + 1
        return [f"{n} item(s) are in the status '{status}', which is not a state of this workflow"
                for status, n in sorted(counts.items())]

    def describe(self, workflow_id: str) -> dict[str, Any]:
        definitions = self._definitions()
        if workflow_id not in definitions:
            raise MissingItem(f"Workflow '{workflow_id}' not found")
        definition = definitions[workflow_id]
        errors, warnings = wf_lib.check(definition)
        return {
            "id": workflow_id, "definition": definition, "used_by": self._used_by(workflow_id),
            "errors": errors, "warnings": warnings + self._stranded(workflow_id, definition),
            "mermaid": wf_lib.to_mermaid(definition),
        }

    def list_all(self) -> dict[str, Any]:
        return {
            "workflows": [self.describe(wid) for wid in self._definitions()],
            "types": {t: cfg.workflow for t, cfg in self.store.hierarchy.types.items()},
            "known_fields": wf_lib.KNOWN_FIELDS,
        }

    def preview(self, definition: Mapping[str, Any], workflow_id: Optional[str] = None) -> dict[str, Any]:
        """Check and draw a definition without saving it."""
        errors, warnings = wf_lib.check(definition)
        normalised = wf_lib.normalise(definition)
        if workflow_id and workflow_id in self.store.hierarchy.workflows and not errors:
            warnings += self._stranded(workflow_id, normalised)
        return {"errors": errors, "warnings": warnings, "definition": normalised,
                "mermaid": wf_lib.to_mermaid(normalised)}

    # -- writing -----------------------------------------------------------------------------

    def _write(self, mutate) -> None:
        with self.store.lock:
            data = copy.deepcopy(self.store.hierarchy_data())
            data.setdefault("workflows", {})
            mutate(data)
            self.store.write_hierarchy(data)

    def save(self, workflow_id: str, definition: Mapping[str, Any]) -> dict[str, Any]:
        if workflow_id not in self.store.hierarchy.workflows:
            raise MissingItem(f"Workflow '{workflow_id}' not found")
        errors, _ = wf_lib.check(definition)
        if errors:
            raise Invalid("; ".join(errors), errors=errors)
        normalised = wf_lib.normalise(definition)
        self._write(lambda data: data["workflows"].__setitem__(workflow_id, normalised))
        return self.describe(workflow_id)

    def create(self, workflow_id: str, copy_from: Optional[str] = None,
               definition: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        if not wf_lib.WORKFLOW_ID.match(workflow_id or ""):
            raise Invalid("A workflow id is lower case letters, digits and underscores, starting with a letter")
        if workflow_id in self.store.hierarchy.workflows:
            raise Conflict(f"Workflow '{workflow_id}' already exists")
        if definition is None:
            if copy_from:
                if copy_from not in self.store.hierarchy.workflows:
                    raise MissingItem(f"Workflow '{copy_from}' not found")
                definition = self._definitions()[copy_from]
            else:
                definition = NEW_WORKFLOW
        errors, _ = wf_lib.check(definition)
        if errors:
            raise Invalid("; ".join(errors), errors=errors)
        normalised = wf_lib.normalise(definition)
        self._write(lambda data: data["workflows"].__setitem__(workflow_id, normalised))
        return self.describe(workflow_id)

    def delete(self, workflow_id: str) -> dict[str, Any]:
        if workflow_id not in self.store.hierarchy.workflows:
            raise MissingItem(f"Workflow '{workflow_id}' not found")
        users = self._used_by(workflow_id)
        if users:
            raise Conflict(f"Workflow '{workflow_id}' is used by: {', '.join(users)}. Assign them another workflow first.",
                           used_by=users)
        if len(self.store.hierarchy.workflows) <= 1:
            raise Conflict("The last workflow cannot be deleted")
        self._write(lambda data: data["workflows"].pop(workflow_id, None))
        return {"deleted": workflow_id}

    def assign(self, type_id: str, workflow_id: str) -> dict[str, Any]:
        if type_id not in self.store.hierarchy.types:
            raise MissingItem(f"Type '{type_id}' not found")
        if workflow_id not in self.store.hierarchy.workflows:
            raise MissingItem(f"Workflow '{workflow_id}' not found")

        def mutate(data):
            data.setdefault("types", {}).setdefault(type_id, {})["workflow"] = workflow_id
        self._write(mutate)
        return {"type": type_id, "workflow": workflow_id, **self.describe(workflow_id)}
