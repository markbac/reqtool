"""Requirement use cases: create, update, bulk update, clone, delete, transition, approve, commit and acceptance criteria."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from reqtool import git_ops
from reqtool.features.reviews import record_approval
from reqtool.fileio import uuid7
from reqtool.store import DuplicateId, HierarchyViolation, ParentCycle, RelationshipViolation, Store, UnknownParent
from . import commit as commit_service
from .errors import (
    Forbidden, Invalid, MergeConflicts, MissingItem, NotFound, OpenTbd, StaleContent, VersionConflict, WorkflowGuard,
)

Publish = Callable[[str, dict], None]

# Fields a client may set to null to clear them. Everything else ignores null (it has no empty value).
CLEARABLE_FIELDS = {
    "parentId", "domain", "discipline", "feature", "owner", "assignee", "component", "iteration",
    "estimate", "estimate_unit", "safety_classification", "safety_standard", "asil_level", "dal_level",
    "mitigates_hazard", "source_document", "legal_compliance_status", "compliance_rationale",
    "target_release", "target_milestone", "planned_start_date", "planned_completion_date",
}

# What a bulk edit may touch. Identity, history, hashes and soft-delete are never bulk-editable.
BULK_EDITABLE_FIELDS = {
    "id", "status", "priority", "owner", "assignee", "component", "domain", "discipline", "feature",
    "iteration", "tags", "allocated_to", "risk", "safety_related", "safety_classification",
    "target_release", "target_milestone", "release_status", "estimate", "estimate_unit",
    "verification_method", "parentId", "attributes", "custom_fields",
}

_NOT_COPIED_ON_CLONE = ("uid", "content_hash", "created", "last_modified", "history",
                        "version", "schema_version", "tool_version", "type")


def merged_view(existing: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    """``existing`` with ``changes`` applied the way an update applies them (one level of nested fields merges)."""
    out = copy.deepcopy(dict(existing))
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **value}
        else:
            out[key] = value
    return out


def changed_fields(sent: Mapping[str, Any]) -> dict[str, Any]:
    """The fields a PUT changes: those the client sent, where an explicit null clears a clearable field."""
    return {k: v for k, v in sent.items() if v is not None or k in CLEARABLE_FIELDS}


class RequirementService:
    def __init__(self, store: Store, publish: Publish, git: Any = git_ops) -> None:
        self.store, self.publish, self.git = store, publish, git

    # -- guards ------------------------------------------------------------------------------

    def _no_merge_conflicts(self) -> None:
        if self.git.has_conflicts(self.store.root):
            raise MergeConflicts()

    def _existing(self, uid: str) -> dict[str, Any]:
        req = self.store.get_requirement(uid)
        if req is None:
            raise NotFound(uid)
        return req

    def _guard_transition(self, req: dict[str, Any], to_state: str) -> None:
        error = self.store.validate_transition(req, to_state)
        if error:
            raise WorkflowGuard(error)

    def _publish_change(self, uid: str, old_status: Any, result: dict[str, Any]) -> None:
        """One event per update: status_changed if the status moved, else requirement_updated."""
        if result.get("status") != old_status:
            self.publish("status_changed", {"uid": uid, "id": result.get("id"), "from": old_status, "to": result.get("status")})
        else:
            self.publish("requirement_updated", {"uid": uid, "id": result.get("id")})

    # -- create / update / delete ------------------------------------------------------------

    def create(self, fields: dict[str, Any]) -> dict[str, Any]:
        self._no_merge_conflicts()
        created = self.store.create_requirement(fields)
        self.publish("requirement_created", {"uid": created["uid"], "id": created.get("id"), "req_type": created.get("req_type")})
        return created

    def update(self, uid: str, changes: dict[str, Any], if_version: Optional[str] = None) -> dict[str, Any]:
        """Update a requirement. ``if_version`` detects a concurrent edit."""
        self._no_merge_conflicts()
        existing = self._existing(uid)
        if if_version and existing.get("version") != if_version:
            raise VersionConflict(if_version, existing.get("version"))
        old_status = existing.get("status")
        new_status = changes.get("status")
        if new_status and new_status != old_status:
            # Guard on the item as it will be, so one request can fill the required fields and move the status.
            self._guard_transition({**merged_view(existing, changes), "status": old_status}, new_status)
        result = self.store.update_requirement(uid, changes, summary="Updated via API")
        if result is None:
            raise NotFound(uid)
        self._publish_change(uid, old_status, result)
        return result

    def delete(self, uid: str) -> dict[str, Any]:
        result = self.store.delete_requirement(uid)
        if result is None:
            raise NotFound(uid)
        self.publish("requirement_deleted", {"uid": uid, "id": result.get("id")})
        return result

    def transitions(self, uid: str) -> dict[str, Any]:
        """Where the item can go next and what each move needs."""
        req = self._existing(uid)
        return {"uid": req["uid"], "id": req.get("id"), "req_type": req.get("req_type"),
                "status": req.get("status"), "transitions": self.store.transition_options(req)}

    def transition(self, uid: str, to_state: str) -> dict[str, Any]:
        """Move to a new status with workflow guard enforcement."""
        req = self._existing(uid)
        if not to_state:
            raise Invalid("to_state is required")
        self._guard_transition(req, to_state)
        old_status = req.get("status")
        result = self.store.update_requirement(uid, {"status": to_state}, summary=f"Transitioned to {to_state}")
        self.publish("status_changed", {"uid": uid, "id": req.get("id"), "from": old_status, "to": to_state})
        return result

    # -- bulk --------------------------------------------------------------------------------

    def bulk_update(self, uids: list[str], fields: dict[str, Any], increment: str, summary: str) -> dict[str, Any]:
        """Same guards as single updates: no writes while the tree has merge conflicts, and a status change must
        be a legal workflow transition for each item."""
        self._no_merge_conflicts()
        forbidden = sorted(set(fields) - BULK_EDITABLE_FIELDS)
        if forbidden:
            raise Invalid(f"Fields not allowed in a bulk update: {', '.join(forbidden)}")
        updated: list[str] = []
        failed: list[str] = []
        errors: dict[str, str] = {}
        changes: list[tuple[str, object, dict]] = []
        new_status = fields.get("status")
        with self.store.lock:  # make the check-then-update atomic per request
            for uid in uids:
                existing = self.store.get_requirement(uid)
                if existing is None:
                    failed.append(uid)
                    errors[uid] = "not found"
                    continue
                if new_status and new_status != existing.get("status"):
                    error = self.store.validate_transition(existing, new_status)
                    if error:
                        failed.append(uid)
                        errors[uid] = error
                        continue
                old_status = existing.get("status")
                try:
                    result = self.store.update_requirement(uid, fields, increment=increment, summary=summary)
                except (ParentCycle, HierarchyViolation, RelationshipViolation, DuplicateId, UnknownParent) as exc:
                    failed.append(uid)
                    errors[uid] = str(exc)
                    continue
                if result:
                    updated.append(uid)
                    changes.append((uid, old_status, dict(result)))
                else:
                    failed.append(uid)
        for uid, old_status, result in changes:
            self._publish_change(uid, old_status, result)
        return {"updated": updated, "failed": failed, "count": len(updated), "errors": errors}

    # -- clone -------------------------------------------------------------------------------

    def clone(self, uid: str, new_id: str = "") -> dict[str, Any]:
        """Duplicate a requirement, clearing history and resetting version."""
        self._no_merge_conflicts()
        src = self._existing(uid)
        fields = copy.deepcopy(src)
        for key in _NOT_COPIED_ON_CLONE:
            fields.pop(key, None)
        if new_id:
            fields["id"] = new_id
        else:
            base = src.get("id", "REQ") + "-COPY"
            fields["id"], n = base, 1
            while self.store.resolve_uid(fields["id"]):  # keep clones unique
                n += 1
                fields["id"] = f"{base}{n}"
        fields["title"] = src.get("title", "") + " (copy)"
        fields["status"] = "draft"
        fields["approval"] = {"status": "draft", "approved_by": None, "approved_date": None}
        fields["verification"] = {"status": "not_started", "verified_date": None, "note": ""}
        created = self.store.create_requirement(fields)
        self._copy_attachment_files(src, created)
        self.publish("requirement_created", {"uid": created["uid"], "id": created.get("id"), "req_type": created.get("req_type")})
        return created

    def _copy_attachment_files(self, src: dict[str, Any], clone: dict[str, Any]) -> None:
        """The clone lists the source's attachments, so give it the files too (else every download is a 404)."""
        import shutil
        src_dir = self.store.attachment_dir(src["uid"])
        if not src_dir.is_dir():
            return
        dest_dir = self.store.attachment_dir(clone["uid"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        for att in clone.get("attachments") or []:
            name = att.get("filename")
            source_file = src_dir / name if name else None
            if source_file is not None and source_file.is_file() and source_file.resolve().is_relative_to(src_dir.resolve()):
                shutil.copy2(source_file, dest_dir / name)

    # -- approval and commit -----------------------------------------------------------------

    def approve(self, uid: str, approved_by: Optional[str], content_hash: Optional[str], user: Mapping[str, Any]) -> dict[str, Any]:
        req = self._existing(uid)
        self._no_merge_conflicts()
        # Who approves is decided by the login, never by the request body.
        if user["authenticated"]:
            if user["role"] not in ("admin", "editor"):
                raise Forbidden("Your role may not approve requirements")
            if approved_by and approved_by != user["username"]:
                raise Forbidden(f"approved_by must be the logged-in user '{user['username']}'")
            approver, verified = user["username"], True
        else:
            approver, verified = approved_by, False  # local single-user mode
        if content_hash and content_hash != req.get("content_hash"):
            raise StaleContent("The requirement changed after you reviewed it: review the new version before approving",
                               content_hash=req.get("content_hash"))
        if req.get("status") != "approved":
            self._guard_transition(req, "approved")
        if self.store.config.validation.block_approval_on_open_tbds:
            open_tbds = self.store.open_tbds_for(req)
            if open_tbds:
                raise OpenTbd("Resolve the open TBD(s) before approval: " + ", ".join(open_tbds), tbds=open_tbds)
        result = self.store.approve_requirement(uid, approver, identity_verified=verified)
        if result is None:
            raise NotFound(uid)
        record_approval(self.store, uid, approver)
        self.publish("requirement_approved", {
            "uid": uid, "id": req.get("id"), "approved_by": approver, "signature": result["approval"]["signature"]})
        return result

    def commit(self, uid: str, message: Optional[str], increment: Optional[str], change_ref: Optional[str]) -> dict[str, Any]:
        req = self._existing(uid)
        store = self.store
        path: Path = store.req_path(uid)
        return commit_service.commit_artefact(
            store, message, path, git=self.git,
            bump=lambda text: store.update_requirement(
                uid, {}, increment=increment or "patch", summary=text, change_ref=change_ref),
            undo=lambda: store.restore_requirement(uid, req),
            version=lambda: (store.get_requirement(uid) or {}).get("version", ""))

    # -- acceptance criteria -----------------------------------------------------------------

    def add_criterion(self, uid: str, text: str, ac_id: Optional[str], links: Optional[list]) -> Optional[dict[str, Any]]:
        req = self._existing(uid)
        ac_uid = uuid7()
        new_ac = {"uid": ac_uid, "id": ac_id or f"{req.get('id', '')}__AC-{ac_uid[:8]}", "text": text, "links": links or []}
        acs = list(req.get("acceptance_criteria", [])) + [new_ac]
        result = self.store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Added acceptance criterion")
        self.publish("requirement_updated", {"uid": uid, "id": req.get("id")})
        return result

    def update_criterion(self, uid: str, ac_uid: str, changes: dict[str, Any]) -> Optional[dict[str, Any]]:
        req = self._existing(uid)
        acs = list(req.get("acceptance_criteria", []))
        for i, ac in enumerate(acs):
            if ac.get("uid") == ac_uid:
                acs[i] = {**ac, **changes}
                result = self.store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Updated acceptance criterion")
                self.publish("requirement_updated", {"uid": uid, "id": req.get("id")})
                return result
        raise MissingItem(f"AC '{ac_uid}' not found")

    def delete_criterion(self, uid: str, ac_uid: str) -> Optional[dict[str, Any]]:
        req = self._existing(uid)
        acs = [ac for ac in req.get("acceptance_criteria", []) if ac.get("uid") != ac_uid]
        result = self.store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Removed acceptance criterion")
        self.publish("requirement_updated", {"uid": uid, "id": req.get("id")})
        return result
