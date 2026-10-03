"""
reqtool.validation
==================
Full validation suite. Returns errors (blocking) and warnings (non-blocking).
Rules follow spec §13.1.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .fileio import (
    compute_requirement_hash,
    compute_principle_hash,
    compute_tbd_hash,
)

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .store import Store


VALE_TIMEOUT_SECONDS = 10  # a stuck Vale process must not hang validation


def run_vale_lint(
    text: str, repo_root: Optional[Path] = None, uid: str = "", field: str = ""
) -> list[dict[str, str]]:
    """
    Run Vale CLI prose linter on text.
    Returns list of warning dicts for any prose style violations.
    """
    if not text or not text.strip():
        return []

    vale_bin = shutil.which("vale")
    if not vale_bin:
        return []

    config_path = None
    if repo_root and (repo_root / ".vale.ini").exists():
        config_path = repo_root / ".vale.ini"
    else:
        bundled = Path(__file__).parent / "defaults" / ".vale.ini"
        if bundled.exists():
            config_path = bundled

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
    except Exception:
        return []

    try:
        cmd = [vale_bin, "--output=JSON"]
        if config_path:
            cmd.append(f"--config={config_path}")
        cmd.append(str(tmp_path))

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                 timeout=VALE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            log.warning("Vale did not finish within %ss; skipping the prose check for this field", VALE_TIMEOUT_SECONDS)
            return []
        if not res.stdout or not res.stdout.strip():
            return []

        try:
            data = json.loads(res.stdout)
        except Exception:
            return []

        warnings: list[dict[str, str]] = []
        for alert_list in data.values():
            if not isinstance(alert_list, list):
                continue
            for alert in alert_list:
                severity = alert.get("Severity", "warning").lower()
                msg = alert.get("Message", "")
                rule = alert.get("Check", "vale.rule")
                line = alert.get("Line", 1)
                code = "VALE_PROSE_ERROR" if severity == "error" else "VALE_PROSE_WARNING"
                warnings.append({
                    "code": code,
                    "message": f"[Line {line}] {msg} ({rule})",
                    "uid": uid,
                    "field": field,
                })
        return warnings
    except Exception:
        return []
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


def _err(code: str, message: str, uid: str = "", field: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "uid": uid, "field": field}


def _warn(code: str, message: str, uid: str = "", field: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "uid": uid, "field": field}


def check_workflow_graph(hierarchy) -> list[tuple[str, str, str]]:
    """Return (code, workflow_id, message) problems in the workflow definitions.

    Every state must be reachable from ``initial``, every transition must point at a
    defined state, and every non-terminal state must be able to reach a terminal one.
    """
    problems: list[tuple[str, str, str]] = []
    for wf_id, wf in hierarchy.workflows.items():
        ids = {s.id if hasattr(s, "id") else s["id"] for s in wf.states}
        terminal = {(s.id if hasattr(s, "id") else s["id"]) for s in wf.states
                    if (s.terminal if hasattr(s, "terminal") else s.get("terminal"))}
        if not ids:
            continue
        for src, targets in wf.transitions.items():
            for t in [src, *targets]:
                if t not in ids:
                    problems.append(("workflow_unknown_state", wf_id,
                                     f"Workflow '{wf_id}' transitions mention undefined state '{t}'"))
        seen, stack = set(), [wf.initial]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(wf.transitions.get(cur, []))
        for sid in sorted(ids - seen):
            problems.append(("workflow_unreachable_state", wf_id,
                             f"State '{sid}' in workflow '{wf_id}' cannot be reached from '{wf.initial}'"))
        for sid in sorted(ids - terminal):
            reach, stack = set(), [sid]
            while stack:
                cur = stack.pop()
                if cur in reach:
                    continue
                reach.add(cur)
                stack.extend(wf.transitions.get(cur, []))
            if not (reach & terminal) and terminal:
                problems.append(("workflow_dead_end", wf_id,
                                 f"State '{sid}' in workflow '{wf_id}' can never reach a terminal state"))
    return problems


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
            req_by_uid=store.requirements,
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

        # Product Principle & NFR Constraint validation (Issue #29)
        p_kind = principle.get("principle_kind") or principle.get("kind")
        nfr_targets = principle.get("nfr_targets") or principle.get("nfr_constraints", {})
        if p_kind == "product_nfr" or nfr_targets:
            if isinstance(nfr_targets, dict):
                for k in nfr_targets.keys():
                    if nfr_keys and k not in nfr_keys:
                        warnings.append(_warn(
                            "unregistered_nfr_key",
                            f"Product principle '{uid}' uses unregistered NFR key '{k}'",
                            uid, "nfr_targets",
                        ))
            satisfied = False
            for req_uid, req in store.requirements.items():
                if req.get("deleted"):
                    continue
                for rel in req.get("relationships", []):
                    tgt = rel.get("target", {}).get("uid") if isinstance(rel.get("target"), dict) else rel.get("target")
                    if tgt == uid:
                        satisfied = True
                        break
                if satisfied:
                    break
                for link in req.get("links", []):
                    if link.get("target_uid") == uid:
                        satisfied = True
                        break
                if satisfied:
                    break
            if not satisfied:
                warnings.append(_warn(
                    "unmapped_product_principle",
                    f"Product NFR principle '{uid}' is not satisfied by any requirement",
                    uid, "principle_kind",
                ))

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

    # Hierarchy rules: child type must be allowed under its parent's type
    if store.hierarchy.enforce != "off":
        for uid, req in store.requirements.items():
            if req.get("deleted"):
                continue
            problem = store.hierarchy_problem(req.get("req_type", "functional"), req.get("parentId"))
            if problem:
                (errors if store.hierarchy.enforce == "error" else warnings).append(
                    (_err if store.hierarchy.enforce == "error" else _warn)(
                        "hierarchy_violation", problem, uid, "parentId"))

    from .stores import hierarchy_store as _hs
    # Parents already in a guarded state (e.g. done) while children are still open
    for uid, req in store.requirements.items():
        if req.get("deleted"):
            continue
        blocking = _hs.open_children(store.hierarchy, store.requirements, req, req.get("status", ""))
        if blocking:
            warnings.append(_warn(
                "open_children",
                f"Status '{req.get('status')}' needs all children closed, but these are not: {', '.join(blocking)}",
                uid, "status"))

    # Approved items whose upstream changed after approval need review
    for uid, req in store.requirements.items():
        if req.get("deleted") or req.get("approval", {}).get("status") != "approved":
            continue
        n = sum(1 for rel in req.get("relationships") or [] if rel.get("suspect"))
        if n:
            warnings.append(_warn(
                "suspect_link",
                f"Approved item has {n} suspect link(s): an upstream item changed after the link was made",
                uid, "relationships"))

    # Workflow definitions must be coherent
    for code, wf_id, message in check_workflow_graph(store.hierarchy):
        warnings.append(_warn(code, message, "", f"workflows.{wf_id}"))

    # Cross-layer relationship rules
    if store.hierarchy.enforce != "off":
        as_error = store.hierarchy.enforce == "error"
        for uid, req in store.requirements.items():
            if req.get("deleted"):
                continue
            for rel in req.get("relationships", []) or []:
                problem = store.relationship_problem(req.get("req_type", "functional"), rel)
                if problem:
                    errors.append(_err("relationship_violation", problem, uid, "relationships")) if as_error \
                        else warnings.append(_warn("relationship_violation", problem, uid, "relationships"))

    # Human IDs must be unique within requirements and within decisions/TBDs
    for label, table in (("requirement", store.requirements), ("decision", getattr(store, "decisions", {}))):
        owners: dict[str, list[str]] = {}
        for uid, item in table.items():
            if not item.get("deleted") and item.get("id"):
                owners.setdefault(item["id"], []).append(uid)
        for rid, uids in owners.items():
            if len(uids) > 1:
                for uid in uids:
                    errors.append(_err("duplicate_id", f"{label} ID '{rid}' is used by {len(uids)} items", uid, "id"))

    # parentId cycles (reported on each member of the loop)
    for uid, req in store.requirements.items():
        if req.get("deleted"):
            continue
        seen = {uid}
        cur = req.get("parentId")
        while cur and cur in store.requirements:
            if cur == uid:
                errors.append(_err("parent_cycle",
                                   "parentId chain loops back to this item", uid, "parentId"))
                break
            if cur in seen:
                break
            seen.add(cur)
            cur = store.requirements[cur].get("parentId")

    # Module lock file checks per product
    _validate_module_locks(store, errors)

    # Approval signatures: forged/tampered signatures are errors; approved content
    # that changed after signing is a warning (it needs re-approval).
    from .auth import check_approval
    for r_uid, r in store.requirements.items():
        if r.get("deleted"):
            continue
        verdict = check_approval(r, store.root)
        if verdict == "invalid":
            errors.append(_err("approval_signature_invalid",
                               "Approval signature does not verify (record altered or signed with another key)",
                               r_uid, "approval.signature"))
        elif verdict == "stale":
            warnings.append(_warn("approval_stale",
                                  "Content changed after it was approved; re-approval required",
                                  r_uid, "approval.signature"))
        elif verdict == "legacy":
            warnings.append(_warn("approval_signature_legacy",
                                  "v1 approval signature does not cover content; re-approve to upgrade",
                                  r_uid, "approval.signature"))

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
    req_by_uid: Optional[dict[str, dict[str, Any]]] = None,
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

        # Schedule dependency conflict check
        if rel_type == "depends_on" and target_uid:
            target_req = (req_by_uid or {}).get(target_uid, {})
            this_rel = req.get("target_release") or req.get("iteration")
            target_rel = target_req.get("target_release") or target_req.get("iteration")
            if this_rel and target_rel and this_rel < target_rel:
                warnings.append(_warn(
                    "schedule_dependency_conflict",
                    f"Item scheduled for '{this_rel}' depends on target {target_uid[:8]}... scheduled for later release '{target_rel}'",
                    uid, "relationships",
                ))

    # parentId
    parent = req.get("parentId")
    if parent and parent not in all_uids:
        errors.append(_err("broken_uid_ref",
                           f"parentId '{parent}' does not exist", uid, "parentId"))

    # Link validation (top-level and acceptance criteria links)
    all_links = list(req.get("links", []))
    for ac in req.get("acceptance_criteria", []):
        all_links.extend(ac.get("links", []))

    for link in all_links:
        sys_val = link.get("system")
        if sys_val and sys_val not in merged_enums.get("link_system", []):
            errors.append(_err("invalid_enum", f"Link system '{sys_val}' is not valid", uid, "links"))
        target_ref = link.get("ref")
        if sys_val in ("rms", "requirement", "principle", "tbd") and target_ref and target_ref not in all_uids:
            errors.append(_err("broken_uid_ref", f"Link target UID '{target_ref}' does not exist", uid, "links"))

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

    comp_status = req.get("legal_compliance_status")
    if comp_status in ("partially_compliant", "non_compliant", "n_a") and not req.get("compliance_rationale"):
        warnings.append(_warn(
            "missing_compliance_rationale",
            f"legal_compliance_status '{comp_status}' requires compliance_rationale explanation",
            uid, "compliance_rationale",
        ))

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
            req_by_uid=store.requirements,
        )
        return {"errors": e, "warnings": w}
    if uid in store.principles:
        e, w = _validate_principle(store.principles[uid], merged_enums)
        return {"errors": e, "warnings": w}
    if uid in store.tbds:
        e, w = _validate_tbd(store.tbds[uid], merged_enums)
        return {"errors": e, "warnings": w}
    return {"errors": [_err("not_found", f"UID '{uid}' not found", uid)], "warnings": []}
