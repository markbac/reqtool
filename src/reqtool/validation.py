"""
reqtool.validation
==================
Full validation suite. Returns errors (blocking) and warnings (non-blocking).
Rules follow spec §13.1.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .fileio import (
    compute_requirement_hash,
    compute_principle_hash,
    compute_tbd_hash,
)

if TYPE_CHECKING:
    from .store import Store


def _err(code: str, message: str, uid: str = "", field: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "uid": uid, "field": field}


def _warn(code: str, message: str, uid: str = "", field: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "uid": uid, "field": field}


def validate_all(store: "Store") -> dict[str, list[dict[str, str]]]:
    """Run full validation. Returns {"errors": [...], "warnings": [...]}."""
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    all_uids = store.all_uids()
    merged_enums = store.merged_enums()
    cfg = store.config.validation
    nfr_keys: set[str] = set(store.repo_enums.nfr_keys)

    # Build map: uid -> status, for supersedes validation
    req_status_by_uid = {uid: r.get("status", "") for uid, r in store.requirements.items()}

    # Build set of open TBDs (for warn_on_open_tbds_in_approved)
    open_tbd_uids: set[str] = {
        uid for uid, t in store.tbds.items()
        if not t.get("deleted") and t.get("status") in ("open", "in_progress")
    }

    known_tags: set[str] = set(store.repo_enums.tags) if store.repo_enums.tags else frozenset()
    known_teams: set[str] = set(store.repo_enums.team) if store.repo_enums.team else frozenset()
    known_owners: set[str] = set(store.repo_enums.owner) if store.repo_enums.owner else frozenset()
    known_safety: set[str] = set(store.repo_enums.safety_class) if store.repo_enums.safety_class else frozenset()

    # Load custom field schema for validation
    custom_field_schema = store.load_custom_field_schema()

    for uid, req in store.requirements.items():
        if req.get("deleted"):
            continue
        e, w = _validate_requirement(
            req, all_uids, merged_enums, cfg, nfr_keys,
            req_status_by_uid, open_tbd_uids,
            known_tags=known_tags, known_teams=known_teams,
            known_owners=known_owners, known_safety=known_safety,
        )
        errors.extend(e)
        warnings.extend(w)
        # Custom field validation
        cf_errors = store.validate_custom_fields(req)
        for cfe in cf_errors:
            errors.append(_err("invalid_custom_field", cfe["message"], uid, cfe["field"]))

    for uid, principle in store.principles.items():
        if principle.get("deleted"):
            continue
        e, w = _validate_principle(principle, merged_enums)
        errors.extend(e)
        warnings.extend(w)

    for uid, tbd in store.tbds.items():
        if tbd.get("deleted"):
            continue
        e, w = _validate_tbd(tbd, merged_enums)
        errors.extend(e)
        warnings.extend(w)

    # Deleted requirement referenced by non-deleted parentId
    deleted_uids = {uid for uid, r in store.requirements.items() if r.get("deleted")}
    for uid, req in store.requirements.items():
        if req.get("deleted"):
            continue
        parent = req.get("parentId")
        if parent and parent in deleted_uids:
            errors.append(_err(
                "deleted_parent_ref",
                f"parentId references deleted requirement {parent}",
                uid, "parentId",
            ))

    # Module lock file checks per product
    _validate_module_locks(store, errors)

    return {"errors": errors, "warnings": warnings}


def _validate_module_locks(store: "Store", errors: list) -> None:
    """Check that lock files exist and match current module file hashes."""
    for product_id, product in store.products.items():
        if not product.get("modules"):
            continue
        lock_path = store.root / "products" / product_id / "_product.lock"
        if not lock_path.exists():
            errors.append(_err(
                "lock_missing",
                f"Product '{product_id}' has modules but _product.lock is missing. Run: req import",
                product_id, "_product.lock",
            ))
            continue
        try:
            from .fileio import load_yaml
            lock = load_yaml(lock_path)
            locked_by_id = {m["id"]: m for m in lock.get("locked", [])}
        except Exception:
            errors.append(_err(
                "lock_invalid",
                f"Product '{product_id}' _product.lock could not be parsed",
                product_id, "_product.lock",
            ))
            continue

        for mod_ref in product.get("modules", []):
            mod_id = mod_ref.get("id")
            if mod_id not in locked_by_id:
                errors.append(_err(
                    "lock_module_missing",
                    f"Module '{mod_id}' listed in product '{product_id}' is not in lock file",
                    product_id, "_product.lock",
                ))
                continue
            locked = locked_by_id[mod_id]
            stored_hash = locked.get("content_hash", "")
            computed = _compute_module_dir_hash(store.root / "modules" / mod_id)
            if stored_hash and computed and stored_hash != computed:
                errors.append(_err(
                    "lock_hash_mismatch",
                    f"Module '{mod_id}' files have changed since lock was generated. Run: req import {mod_id}",
                    product_id, "_product.lock",
                ))


def _compute_module_dir_hash(module_dir: Path) -> str:
    """Compute a hash over all requirement files in a module directory."""
    if not module_dir.exists():
        return ""
    files = sorted(p for p in module_dir.glob("*.yaml") if not p.name.startswith("_"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.read_bytes())
    return f"sha256:{h.hexdigest()}"


def _validate_requirement(
    req: dict[str, Any],
    all_uids: set[str],
    merged_enums: dict[str, Any],
    cfg: Any,
    nfr_keys: set[str],
    req_status_by_uid: dict[str, str],
    open_tbd_uids: set[str],
    known_tags: set[str] = frozenset(),
    known_teams: set[str] = frozenset(),
    known_owners: set[str] = frozenset(),
    known_safety: set[str] = frozenset(),
) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    uid = req.get("uid", "")

    # Required fields
    for field in ("uid", "id", "title", "schema_version", "type", "version",
                  "status", "priority", "req_type"):
        if not req.get(field):
            errors.append(_err("missing_required_field",
                               f"Required field '{field}' is missing or empty", uid, field))

    content = req.get("content", {})
    if not content.get("description"):
        errors.append(_err("missing_required_field",
                           "content.description is required", uid, "content.description"))

    for ts_field in ("created", "last_modified"):
        if not req.get(ts_field):
            errors.append(_err("missing_required_field",
                               f"Required field '{ts_field}' is missing", uid, ts_field))

    # AC required when approved
    approval_status = req.get("approval", {}).get("status", "")
    if approval_status == "approved" and not req.get("acceptance_criteria"):
        errors.append(_err("approved_no_ac",
                           "Approved requirement must have at least one acceptance criterion",
                           uid, "acceptance_criteria"))

    # Content hash
    stored_hash = req.get("content_hash", "")
    computed = compute_requirement_hash(req)
    if stored_hash and stored_hash != computed:
        errors.append(_err("hash_mismatch",
                           "content_hash does not match recomputation (manual edit bypassed tool?)",
                           uid, "content_hash"))

    # Version drift: hash changed but version still 1.0.0 (heuristic)
    # Full check: if stored_hash != computed we already flagged it above.
    # Extra: if content_hash is empty, warn.
    if not stored_hash:
        warnings.append(_warn("missing_hash",
                              "content_hash is empty -- requirement was likely created outside the tool",
                              uid, "content_hash"))

    # Enum validation
    for field, enum_key in (
        ("status", "status"),
        ("priority", "priority"),
        ("req_type", "req_type"),
        ("risk", "risk_level"),
        ("verification_method", "verification_method"),
    ):
        val = req.get(field)
        if val and val not in merged_enums.get(enum_key, []):
            errors.append(_err("invalid_enum",
                               f"'{field}' value '{val}' not in enum {enum_key}", uid, field))

    if approval_status and approval_status not in merged_enums.get("approval_status", []):
        errors.append(_err("invalid_enum",
                           f"approval.status '{approval_status}' not valid", uid, "approval.status"))

    verification_status = req.get("verification", {}).get("status", "")
    if verification_status and verification_status not in merged_enums.get("verification_status", []):
        errors.append(_err("invalid_enum",
                           f"verification.status '{verification_status}' not valid",
                           uid, "verification.status"))

    implementation_status = req.get("implementation", {}).get("status", "")
    if implementation_status and implementation_status not in merged_enums.get("implementation_status", []):
        errors.append(_err("invalid_enum",
                           f"implementation.status '{implementation_status}' not valid",
                           uid, "implementation.status"))

    # Relationship checks
    for rel in req.get("relationships", []):
        target_uid = rel.get("target", {}).get("uid", "")
        rel_type = rel.get("type", "")

        if target_uid and target_uid not in all_uids:
            errors.append(_err("broken_uid_ref",
                               f"Relationship target UID '{target_uid}' does not exist",
                               uid, "relationships"))

        if rel_type and rel_type not in merged_enums.get("relationship_type", []):
            errors.append(_err("invalid_enum",
                               f"Relationship type '{rel_type}' is not valid", uid, "relationships"))

        # supersedes target must be deprecated
        if rel_type == "supersedes" and target_uid:
            target_status = req_status_by_uid.get(target_uid, "")
            if target_status and target_status != "deprecated":
                errors.append(_err(
                    "supersedes_not_deprecated",
                    f"'supersedes' target {target_uid[:8]}... has status '{target_status}' -- must be 'deprecated'",
                    uid, "relationships",
                ))

    # parentId
    parent = req.get("parentId")
    if parent and parent not in all_uids:
        errors.append(_err("broken_uid_ref",
                           f"parentId '{parent}' does not exist", uid, "parentId"))

    # negative requires positive_counterpart
    if req.get("attributes", {}).get("negative"):
        has_counterpart = any(
            r.get("type") == "positive_counterpart"
            for r in req.get("relationships", [])
        )
        if not has_counterpart:
            errors.append(_err(
                "negative_no_counterpart",
                "attributes.negative: true requires a positive_counterpart relationship",
                uid, "attributes.negative",
            ))

    # NFR key validation
    nfr = req.get("nfr", {})
    if nfr_keys:
        for key in nfr:
            if key not in nfr_keys:
                warnings.append(_warn(
                    "unknown_nfr_key",
                    f"nfr key '{key}' is not in enums.yaml nfr_keys -- register it to suppress this warning",
                    uid, f"nfr.{key}",
                ))

    # --- Warnings ---

    if cfg.require_rationale_for_approved and approval_status == "approved":
        if not content.get("rationale"):
            warnings.append(_warn("missing_rationale",
                                  "Approved requirement has no rationale", uid, "content.rationale"))

    if cfg.require_owner and not req.get("owner"):
        warnings.append(_warn("missing_owner", "No owner assigned", uid, "owner"))

    if req.get("verification_method") == "test" and cfg.warn_on_missing_test_ref:
        has_test_link = any(
            link.get("type") == "test_case"
            for ac in req.get("acceptance_criteria", [])
            for link in ac.get("links", [])
        )
        if not has_test_link:
            warnings.append(_warn(
                "missing_test_ref",
                "verification_method is 'test' but no test_case links on any AC",
                uid, "acceptance_criteria",
            ))

    # open TBDs on approved requirement
    if cfg.warn_on_open_tbds_in_approved and approval_status == "approved":
        for link in req.get("links", []):
            if link.get("type") == "tbd" and link.get("ref") in open_tbd_uids:
                warnings.append(_warn(
                    "open_tbd_on_approved",
                    f"Approved requirement links to open TBD {link.get('ref', '')[:8]}...",
                    uid, "links",
                ))

    history = req.get("history", [])
    if len(history) >= 15:
        warnings.append(_warn("history_near_cap",
                              f"History has {len(history)} entries (cap is 20)", uid, "history"))

    if req.get("implementation", {}).get("branch") and verification_status == "passed":
        warnings.append(_warn(
            "branch_on_verified",
            "implementation.branch is set on a verified requirement",
            uid, "implementation.branch",
        ))

    if req.get("attributes", {}).get("maturity") == "low" and approval_status == "approved":
        warnings.append(_warn(
            "low_maturity_approved",
            "Approved requirement has attributes.maturity: low",
            uid, "attributes.maturity",
        ))

    # Unknown tags (only warn if the vocabulary is non-empty)
    if known_tags:
        for tag in req.get("tags", []):
            if tag not in known_tags:
                warnings.append(_warn(
                    "unknown_tag",
                    f"Tag '{tag}' is not in the vocabulary. Add it via ⊙ Vocab or enums.yaml",
                    uid, "tags",
                ))

    # Unknown teams
    if known_teams:
        for team in req.get("allocated_to", []):
            if team not in known_teams:
                warnings.append(_warn(
                    "unknown_team",
                    f"Team '{team}' is not in the vocabulary. Add it via ⊙ Vocab or enums.yaml",
                    uid, "allocated_to",
                ))

    # Unknown owner
    if known_owners:
        owner = req.get("owner")
        if owner and owner not in known_owners:
            warnings.append(_warn(
                "unknown_owner",
                f"Owner '{owner}' is not in the people list. Add via ⊙ Vocab or enums.yaml",
                uid, "owner",
            ))

    # Unknown safety classification
    if known_safety and req.get("safety_related"):
        sc = req.get("safety_classification")
        if sc and sc not in known_safety:
            warnings.append(_warn(
                "unknown_safety_class",
                f"Safety classification '{sc}' is not in the vocabulary. Add via ⊙ Vocab or enums.yaml",
                uid, "safety_classification",
            ))

    return errors, warnings


def _validate_principle(
    principle: dict[str, Any],
    merged_enums: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    uid = principle.get("uid", "")

    for field in ("uid", "id", "title", "schema_version", "type", "version", "status"):
        if not principle.get(field):
            errors.append(_err("missing_required_field",
                               f"Required field '{field}' missing", uid, field))

    stored_hash = principle.get("content_hash", "")
    computed = compute_principle_hash(principle)
    if stored_hash and stored_hash != computed:
        errors.append(_err("hash_mismatch",
                           "content_hash does not match recomputation", uid, "content_hash"))

    approval_status = principle.get("approval", {}).get("status")
    if approval_status and approval_status not in merged_enums.get("approval_status", []):
        errors.append(_err("invalid_enum",
                           f"approval.status '{approval_status}' is not valid", uid, "approval.status"))

    if not principle.get("content", {}).get("description"):
        warnings.append(_warn("missing_description",
                              "Principle has no description", uid, "content.description"))

    return errors, warnings


def _validate_tbd(
    tbd: dict[str, Any],
    merged_enums: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    uid = tbd.get("uid", "")

    for field in ("uid", "id", "title", "schema_version", "type", "version", "status"):
        if not tbd.get(field):
            errors.append(_err("missing_required_field",
                               f"Required field '{field}' missing", uid, field))

    stored_hash = tbd.get("content_hash", "")
    computed = compute_tbd_hash(tbd)
    if stored_hash and stored_hash != computed:
        errors.append(_err("hash_mismatch",
                           "content_hash does not match recomputation", uid, "content_hash"))

    status = tbd.get("status")
    if status and status not in merged_enums.get("tbd_status", []):
        errors.append(_err("invalid_enum",
                           f"status '{status}' is not valid", uid, "status"))

    priority = tbd.get("priority")
    if priority and priority not in merged_enums.get("priority", []):
        errors.append(_err("invalid_enum",
                           f"priority '{priority}' is not valid", uid, "priority"))

    return errors, warnings


def validate_single(store: "Store", uid: str) -> dict[str, list[dict[str, str]]]:
    """Validate a single artefact by UID."""
    all_uids = store.all_uids()
    merged_enums = store.merged_enums()
    cfg = store.config.validation
    nfr_keys = set(store.repo_enums.nfr_keys)
    req_status_by_uid = {u: r.get("status", "") for u, r in store.requirements.items()}
    open_tbd_uids = {
        u for u, t in store.tbds.items()
        if not t.get("deleted") and t.get("status") in ("open", "in_progress")
    }

    if uid in store.requirements:
        known_tags: set[str] = set(store.repo_enums.tags) if store.repo_enums.tags else frozenset()
        known_teams: set[str] = set(store.repo_enums.team) if store.repo_enums.team else frozenset()
        known_owners: set[str] = set(store.repo_enums.owner) if store.repo_enums.owner else frozenset()
        known_safety: set[str] = set(store.repo_enums.safety_class) if store.repo_enums.safety_class else frozenset()
        e, w = _validate_requirement(
            store.requirements[uid], all_uids, merged_enums, cfg,
            nfr_keys, req_status_by_uid, open_tbd_uids,
            known_tags=known_tags, known_teams=known_teams,
            known_owners=known_owners, known_safety=known_safety,
        )
        return {"errors": e, "warnings": w}
    if uid in store.principles:
        e, w = _validate_principle(store.principles[uid], merged_enums)
        return {"errors": e, "warnings": w}
    if uid in store.tbds:
        e, w = _validate_tbd(store.tbds[uid], merged_enums)
        return {"errors": e, "warnings": w}
    return {"errors": [_err("not_found", f"UID '{uid}' not found", uid)], "warnings": []}
