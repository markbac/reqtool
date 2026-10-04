"""
reqtool.store
=============
In-memory graph of all artefacts loaded from the repository.
Provides lookup by UID, tree construction, validation, and mutation helpers.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from .fileio import (
    load_yaml,
    save_yaml,
    compute_requirement_hash,
    compute_principle_hash,
    compute_tbd_hash,
    bump_version,
    utcnow_iso,
    uuid7,
    validate_id,
)
from .models import (
    RepoConfig,
    CoreEnums,
    RepoEnums,
    HierarchyConfig,
    HierarchyWorkflowDef,
    ChecklistItem,
)

log = logging.getLogger(__name__)

from . import __version__ as TOOL_VERSION
from .actor import resolve_author


import functools
import threading


class ParentCycle(ValueError):
    """Re-parenting would make an item its own ancestor."""


class UnknownParent(ValueError):
    """``parentId`` does not name a live requirement."""


class DuplicateId(ValueError):
    """Another requirement already uses this human-readable ID."""


class RelationshipViolation(ValueError):
    """A relationship type is not allowed between these item types (hierarchy.enforce: error)."""


class HierarchyViolation(ValueError):
    """The child type is not allowed under the parent type (hierarchy.enforce: error)."""

from .stores import attachment_store, comment_store, hierarchy_store


def substitute_template_variables(val: Any, variables: dict[str, Any]) -> Any:
    """Recursively substitute {{var_name}} and {{var.var_name}} template expressions."""
    if not variables or not val:
        return val
    if isinstance(val, str):
        res = val
        for k, v in variables.items():
            pattern1 = "{{" + k + "}}"
            pattern2 = "{{var." + k + "}}"
            res = res.replace(pattern1, str(v)).replace(pattern2, str(v))
        return res
    if isinstance(val, dict):
        return {k: substitute_template_variables(v, variables) for k, v in val.items()}
    if isinstance(val, list):
        return [substitute_template_variables(item, variables) for item in val]
    return val


_REMOTE_SCHEMES = ("http", "https", "ssh", "git")
_SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[A-Za-z0-9._~/-]+$")
_REMOTE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


def _validate_remote_url(url: str) -> None:
    """Allow only plain http(s)/ssh/git URLs or scp-style ``user@host:path``.

    Rejects option-like values (leading ``-``, e.g. ``--upload-pack=...``),
    whitespace/control characters, ``ext::``/``file:`` transports and local paths.
    """
    from urllib.parse import urlparse

    if not url or url.startswith("-") or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("Unsupported git remote")
    if _SCP_LIKE_RE.match(url):
        return
    parsed = urlparse(url)
    if parsed.scheme not in _REMOTE_SCHEMES or not parsed.hostname:
        raise ValueError(f"Unsupported git remote URI scheme for '{url}'")


def _validate_remote_ref(ref: str) -> None:
    if not _REMOTE_REF_RE.match(ref) or ".." in ref:
        raise ValueError(f"Invalid git_ref '{ref}'")


def _git_remote(args: list[str], cwd: Path) -> None:
    """Run git for a network operation: restricted transports, no prompts, timeout."""
    import os
    import subprocess

    cmd = [
        "git",
        "-c", "protocol.allow=never",
        "-c", "protocol.https.allow=always",
        "-c", "protocol.http.allow=always",
        "-c", "protocol.ssh.allow=always",
        "-c", "protocol.git.allow=always",
        *args,
    ]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env, timeout=180)
    except subprocess.TimeoutExpired:
        raise ValueError(f"git {args[0]} timed out")
    if res.returncode != 0:
        raise ValueError(f"git {args[0]} failed: {(res.stderr or res.stdout).strip()[:500]}")


def _locked(fn):
    """Run a Store method while holding the store's re-entrant lock.

    Mutators are read-modify-write sequences over shared dicts and YAML files;
    without this, concurrent requests lose each other's updates.
    """
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)
    return wrapper


class Store:
    """
    Holds all loaded artefacts in memory.
    Call load() to populate from disk.
    """

    def __init__(self, repo_root: Path = Path(".")) -> None:
        self.root = repo_root
        self._lock = threading.RLock()
        self.config: RepoConfig = RepoConfig()
        self.core_enums: CoreEnums = CoreEnums()
        self.repo_enums: RepoEnums = RepoEnums()
        self.hierarchy: HierarchyConfig = HierarchyConfig()

        self.requirements: dict[str, dict[str, Any]] = {}
        self.principles: dict[str, dict[str, Any]] = {}
        self.decisions: dict[str, dict[str, Any]] = {}
        self.modules: dict[str, dict[str, Any]] = {}
        self.products: dict[str, dict[str, Any]] = {}
        self.module_requirements: dict[str, dict[str, dict[str, Any]]] = {}
        # Where each artefact was loaded from, so a file whose name is not its uid is rewritten in place
        # instead of being duplicated under <uid>.yaml.
        self._file_for: dict[tuple[str, str], Path] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load (or reload) all artefacts from the repository root."""
        with self._lock:
            # Build the new state aside and swap it in, so a concurrent reader never sees a half-loaded store.
            self._file_for = {}
            new_reqs: dict[str, dict[str, Any]] = {}
            new_principles: dict[str, dict[str, Any]] = {}
            new_decisions: dict[str, dict[str, Any]] = {}
            self.modules = {}
            self.products = {}
            self.module_requirements = {}

            self._load_config()
            self._load_enums()
            self._load_hierarchy()
            self._load_dir(self.root / "requirements", new_reqs, "requirements")
            for req in new_reqs.values():
                # Older files used `iteration_id`; `iteration` is the one field the editor and filters use.
                legacy = req.pop("iteration_id", None)
                if legacy and not req.get("iteration"):
                    req["iteration"] = legacy
            self._load_dir(self.root / "principles", new_principles, "principles")
            self._load_dir(self.root / "decisions", new_decisions, "decisions")
            self._load_dir(self.root / "tbds", new_decisions, "decisions")
            self.requirements, self.principles, self.decisions = new_reqs, new_principles, new_decisions
            self._load_modules()
            self._load_products()
            log.info(
                "Store loaded: %d requirements, %d principles, %d decisions/TBDs, "
                "%d modules, %d products",
                len(self.requirements), len(self.principles), len(self.decisions),
                len(self.modules), len(self.products),
            )

    def _load_config(self) -> None:
        cfg_path = self.root / ".reqtool" / "config.yaml"
        if cfg_path.exists():
            data = load_yaml(cfg_path)
            self.config = RepoConfig.model_validate(data)

    def _load_enums(self) -> None:
        enums_path = self.root / ".reqtool" / "enums.yaml"
        if enums_path.exists():
            data = load_yaml(enums_path)
            self.repo_enums = RepoEnums.model_validate(data)

    def _load_hierarchy(self) -> None:
        """Load hierarchy.yaml from project, falling back to bundled defaults."""
        self.hierarchy = hierarchy_store.load_hierarchy(self.root)

    def _parse_hierarchy(self, data: dict) -> HierarchyConfig:
        """Parse hierarchy YAML into HierarchyConfig, handling nested guards."""
        from .models import (
            ItemTypeConfig, HierarchyRule, HierarchyWorkflowDef,
            HierarchyWorkflowState, WorkflowGuard, CrossLayerRule, RelationshipTypeDef,
        )
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
            states = [HierarchyWorkflowState.model_validate(s) for s in wf_data.get("states", [])]
            wf = HierarchyWorkflowDef(
                initial=wf_data.get("initial", "draft"),
                states=states,
                transitions=wf_data.get("transitions", {}),
                guards=guards,
            )
            workflows[wf_id] = wf
        cross_layer = [CrossLayerRule.model_validate(r) for r in (data.get("cross_layer_rules") or [])]
        rel_types = [RelationshipTypeDef.model_validate(r) for r in (data.get("default_relationship_types") or [])]
        return HierarchyConfig(
            types=types,
            hierarchy=hierarchy,
            workflows=workflows,
            dor=data.get("dor") or {},
            dod=data.get("dod") or {},
            type_fields=data.get("type_fields") or {},
            cross_layer_rules=cross_layer,
            default_relationship_types=rel_types,
        )

    def _load_dir(self, directory: Path, target: dict, kind: str) -> None:
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            try:
                data = load_yaml(path)
                uid = data.get("uid")
                if uid:
                    if uid in target:
                        log.warning("Duplicate uid %s in %s and %s: using the later file",
                                    uid, self._file_for.get((kind, uid)), path)
                    target[uid] = data
                    self._file_for[(kind, uid)] = path
            except Exception as exc:
                log.warning("Failed to load %s: %s", path, exc)

    def _load_modules(self) -> None:
        modules_dir = self.root / "modules"
        if not modules_dir.exists():
            return
        for module_dir in sorted(modules_dir.iterdir()):
            if not module_dir.is_dir():
                continue
            manifest = module_dir / "_module.yaml"
            if not manifest.exists():
                continue
            try:
                data = load_yaml(manifest)
                if not isinstance(data, dict):
                    log.warning("Skipping module %s: manifest is not a mapping", module_dir)
                    continue
                module_id = data.get("id") or module_dir.name
                self.modules[module_id] = data
                reqs: dict[str, dict] = {}
                for req_path in sorted(module_dir.glob("*.yaml")):
                    if req_path.name.startswith("_"):
                        continue
                    try:
                        req_data = load_yaml(req_path)
                        if not isinstance(req_data, dict):
                            continue
                        uid = req_data.get("uid")
                        if uid:
                            reqs[uid] = req_data
                    except Exception as exc:
                        log.warning("Failed to load module req %s: %s", req_path, exc)
                self.module_requirements[module_id] = reqs
            except Exception as exc:
                log.warning("Failed to load module %s: %s", module_dir, exc)

    def _load_products(self) -> None:
        products_dir = self.root / "products"
        if not products_dir.exists():
            return
        for product_dir in sorted(products_dir.iterdir()):
            if not product_dir.is_dir():
                continue
            manifest = product_dir / "_product.yaml"
            if not manifest.exists():
                continue
            try:
                data = load_yaml(manifest)
                if not isinstance(data, dict):
                    log.warning("Skipping product %s: manifest is not a mapping", product_dir)
                    continue
                product_id = data.get("id") or product_dir.name
                self.products[product_id] = data
            except Exception as exc:
                log.warning("Failed to load product %s: %s", product_dir, exc)

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def all_uids(self) -> set[str]:
        uids: set[str] = set()
        uids.update(self.requirements)
        uids.update(self.principles)
        uids.update(self.decisions)
        for reqs in self.module_requirements.values():
            uids.update(reqs)
        return uids

    def get_requirement(self, uid: str) -> Optional[dict]:
        return self.requirements.get(uid)

    def get_principle(self, uid: str) -> Optional[dict]:
        return self.principles.get(uid)

    def get_decision(self, uid: str) -> Optional[dict]:
        return self.decisions.get(uid)

    def get_tbd(self, uid: str) -> Optional[dict]:
        return self.get_decision(uid)

    def merged_enums(self) -> dict[str, Any]:
        """Return core + repo enums merged."""
        result = self.core_enums.model_dump()
        repo = self.repo_enums.model_dump()
        for key, values in repo.items():
            if isinstance(values, list) and values:
                if key in result and isinstance(result[key], list):
                    # Extend core with repo-only values
                    existing = set(result[key])
                    result[key] = result[key] + [v for v in values if v not in existing]
                else:
                    result[key] = values
            elif isinstance(values, dict) and values:
                result[key] = values
        return result

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def req_path(self, uid: str) -> Path:
        return self._file_for.get(("requirements", uid)) or self.root / "requirements" / f"{uid}.yaml"

    def principle_path(self, uid: str) -> Path:
        return self._file_for.get(("principles", uid)) or self.root / "principles" / f"{uid}.yaml"

    def decision_path(self, uid: str) -> Path:
        """File for a decision or TBD. Files not yet migrated stay in the legacy ``tbds/`` folder."""
        recorded = self._file_for.get(("decisions", uid))
        if recorded is not None:
            return recorded
        legacy = self.root / "tbds" / f"{uid}.yaml"
        if legacy.exists():
            return legacy
        return self.root / "decisions" / f"{uid}.yaml"

    # ------------------------------------------------------------------
    # Tree construction
    # ------------------------------------------------------------------

    def build_tree(self, product_id: Optional[str] = None, variant: Optional[str] = None) -> list[dict]:
        """
        Return a nested tree for the given product.
        Each node: {uid, id, title, status, type, children: [...]}
        """
        all_reqs = dict(self.requirements)

        # Include module requirements for this product, applying overlays and overrides
        if product_id and product_id in self.products:
            product = self.products[product_id]
            prod_vars = product.get("variables", {}) or product.get("parameters", {}) or {}

            for mod_ref in product.get("modules", []):
                mod_id = mod_ref.get("id")
                overrides = mod_ref.get("overrides", {}) or {}
                overlay = mod_ref.get("overlay", {}) or mod_ref.get("overlays", {}) or {}
                mod_vars = {**prod_vars, **(mod_ref.get("variables", {}) or mod_ref.get("parameters", {}) or {})}

                module = self.modules.get(mod_id, {})
                overrideable: set[str] = set(module.get("overrideable", []))

                if mod_id in self.module_requirements:
                    for uid, req in self.module_requirements[mod_id].items():
                        if uid not in all_reqs:
                            merged = {**req, "_module": mod_id}
                            # Product Overlay (Issue #31)
                            if uid in overlay:
                                merged = {**merged, **overlay[uid]}
                            # Per-UID overrides from product manifest
                            if uid in overrides:
                                uid_overrides = overrides[uid]
                                for field, value in uid_overrides.items():
                                    if field in overrideable:
                                        if "." in field:
                                            top, sub = field.split(".", 1)
                                            if isinstance(merged.get(top), dict):
                                                merged[top] = {**merged[top], sub: value}
                                        else:
                                            merged[field] = value
                            # Template Variable Substitution (Issue #30)
                            if mod_vars:
                                merged = substitute_template_variables(merged, mod_vars)
                            all_reqs[uid] = merged

        # Filter variant if specified
        if variant:
            attr_key = f"variant_{variant}"
            filtered: dict[str, dict] = {}
            for uid, req in all_reqs.items():
                attrs = req.get("attributes", {})
                # Include if the variant key is absent (applies to all) or true
                if attrs.get(attr_key, True) is not False:
                    filtered[uid] = req
            all_reqs = filtered

        # Exclude deleted
        active = {uid: r for uid, r in all_reqs.items() if not r.get("deleted", False)}

        # Build children map
        children_map: dict[Optional[str], list[dict]] = {}
        for uid, req in active.items():
            parent = req.get("parentId")
            children_map.setdefault(parent, []).append(req)

        def node(req: dict, path: frozenset = frozenset()) -> dict:
            uid = req["uid"]
            path = path | {uid}  # guard against parentId cycles in existing data
            return {
                "uid": uid,
                "id": req.get("id", ""),
                "title": req.get("title", ""),
                "status": req.get("status", "draft"),
                "priority": req.get("priority", "medium"),
                "req_type": req.get("req_type", "functional"),
                "domain": req.get("domain"),
                "module": req.get("_module"),
                "owner": req.get("owner"),
                "suspect_count": sum(1 for r in req.get("relationships") or [] if r.get("suspect")),
                "children": [node(c, path) for c in sorted(
                    (c for c in children_map.get(uid, []) if c["uid"] not in path),
                    key=lambda r: r.get("id", r.get("uid", "")),
                )],
            }

        roots = children_map.get(None, [])

        # If product specifies root_requirements, use that ordering
        if product_id and product_id in self.products:
            ordered_uids = [
                r["uid"] for r in self.products[product_id].get("root_requirements", [])
            ]
            if ordered_uids:
                roots_by_uid = {r["uid"]: r for r in roots}
                ordered_roots = [roots_by_uid[u] for u in ordered_uids if u in roots_by_uid]
                remaining = [r for r in roots if r["uid"] not in set(ordered_uids)]
                roots = ordered_roots + remaining

        local_roots = [r for r in roots if not r.get("_module")]
        module_roots_by_mod: dict[str, list[dict]] = {}
        for r in roots:
            mod = r.get("_module")
            if mod:
                module_roots_by_mod.setdefault(mod, []).append(r)

        # Also include modules that are listed in the product but have no root reqs
        if product_id and product_id in self.products:
            for mod_ref in self.products[product_id].get("modules", []):
                mod_id = mod_ref.get("id")
                if mod_id and mod_id not in module_roots_by_mod:
                    module_roots_by_mod[mod_id] = []

        tree: list[dict] = [node(r) for r in sorted(local_roots, key=lambda r: r.get("id", r.get("uid", "")))]

        # Append synthetic module group nodes
        for mod_id, mod_roots in module_roots_by_mod.items():
            module_manifest = self.modules.get(mod_id, {})
            group: dict[str, Any] = {
                "uid": f"__module__{mod_id}",
                "id": mod_id,
                "title": module_manifest.get("title", mod_id),
                "_is_module_group": True,
                "module": mod_id,
                "children": [node(r) for r in sorted(mod_roots, key=lambda r: r.get("id", r.get("uid", "")))],
            }
            tree.append(group)

        return tree

    # ------------------------------------------------------------------
    # Write helpers: requirement
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise_requirement(fields: dict[str, Any]) -> dict[str, Any]:
        """
        Strip client-side display fields and normalise before saving.
        - Removes _display from each relationship (UI-only annotation).
        - Replaces ephemeral AC UIDs (not valid UUIDv7) with proper UUIDv7.
        - Strips internal _* keys from the top level.
        """
        from .fileio import uuid7

        result = {k: v for k, v in fields.items() if not k.startswith("_")}

        # Strip _display from relationships
        rels = result.get("relationships")
        if isinstance(rels, list):
            result["relationships"] = [
                {k: v for k, v in rel.items() if k != "_display"}
                for rel in rels
            ]

        # Fix ephemeral AC UIDs
        acs = result.get("acceptance_criteria")
        if isinstance(acs, list):
            cleaned = []
            for ac in acs:
                uid = ac.get("uid", "")
                # Ephemeral UIDs contain 'new-' prefix or are just timestamps
                if not uid or uid.startswith("new-") or len(uid) < 32:
                    ac = {**ac, "uid": uuid7()}
                cleaned.append(ac)
            result["acceptance_criteria"] = cleaned

        return result

    @_locked
    def create_requirement(self, fields: dict[str, Any], author: str = "reqtool") -> dict[str, Any]:
        fields = self._sanitise_requirement(fields)
        uid = uuid7()
        now = utcnow_iso()
        req_type = fields.get("req_type", "functional")
        self._check_parent_exists(fields.get("parentId"))
        self._check_hierarchy(req_type, fields.get("parentId"))
        self._check_relationships(req_type, fields.get("relationships") or [], [])
        if fields.get("id"):
            self._check_id(fields["id"], None)

        # Determine default status from workflow initial state
        wf = self.get_workflow_for_type(req_type)
        default_status = wf.initial if wf else "draft"

        # Auto-increment ID if not provided
        provided_id = fields.get("id")
        if not provided_id:
            provided_id = self.next_id_for_type(req_type)

        # Populate DoR/DoD from hierarchy defaults if not provided
        dor = fields.get("dor_checklist") or self.default_checklist("dor", req_type)
        dod = fields.get("dod_checklist") or self.default_checklist("dod", req_type)

        data: dict[str, Any] = {
            "schema_version": "1.0.0",
            "type": "requirement",
            "tool_version": TOOL_VERSION,
            "uid": uid,
            "id": provided_id,
            "parentId": fields.get("parentId"),
            "title": fields.get("title", ""),
            "version": "1.0.0",
            "content": fields.get("content", {"description": "", "rationale": "", "extended_description": ""}),
            "acceptance_criteria": fields.get("acceptance_criteria", []),
            "status": fields.get("status", default_status),
            "priority": fields.get("priority", "medium"),
            "req_type": req_type,
            "domain": fields.get("domain"),
            "feature": fields.get("feature"),
            "discipline": fields.get("discipline"),
            "owner": fields.get("owner"),
            "assignee": fields.get("assignee"),
            "component": fields.get("component"),
            "allocated_to": fields.get("allocated_to", []),
            "tags": fields.get("tags", []),
            "iteration": fields.get("iteration"),
            "estimate": fields.get("estimate"),
            "estimate_unit": fields.get("estimate_unit"),
            "dor_checklist": dor,
            "dod_checklist": dod,
            "attributes": fields.get("attributes", {}),
            "custom_fields": fields.get("custom_fields", {}),
            "nfr": fields.get("nfr", {}),
            "constraints": fields.get("constraints", []),
            "assumptions": fields.get("assumptions", []),
            "relationships": fields.get("relationships", []),
            "links": fields.get("links", []),
            "attachments": fields.get("attachments", []),
            "risk": fields.get("risk", "none"),
            "safety_related": fields.get("safety_related", False),
            "safety_classification": fields.get("safety_classification"),
            "safety_standard": fields.get("safety_standard"),
            "asil_level": fields.get("asil_level"),
            "dal_level": fields.get("dal_level"),
            "mitigates_hazard": fields.get("mitigates_hazard"),
            "source_document": fields.get("source_document"),
            "legal_compliance_status": fields.get("legal_compliance_status"),
            "compliance_rationale": fields.get("compliance_rationale"),
            "target_release": fields.get("target_release"),
            "target_milestone": fields.get("target_milestone"),
            "release_status": fields.get("release_status", "unassigned"),
            "planned_start_date": fields.get("planned_start_date"),
            "planned_completion_date": fields.get("planned_completion_date"),
            "verification_method": fields.get("verification_method", "test"),
            "verification": fields.get("verification", {"status": "not_started", "verified_date": None, "note": ""}),
            "approval": fields.get("approval", {"status": "draft", "approved_by": None, "approved_date": None}),
            "review": fields.get("review", {"last_reviewed": None, "reviewers": [], "note": ""}),
            "implementation": fields.get("implementation", {"status": "not_started", "branch": None}),
            "content_hash": "",
            "created": now,
            "last_modified": now,
            "deleted": False,
            "history": [{"version": "1.0.0", "date": now, "modified_by": resolve_author(author),
                         "summary": "Initial draft.", "commit_sha": None, "change_ref": None}],
        }
        data["content_hash"] = compute_requirement_hash(data)
        self.requirements[uid] = data
        save_yaml(self.req_path(uid), data)
        return data

    @_locked
    def update_requirement(
        self, uid: str, fields: dict[str, Any],
        increment: str = "patch", author: str = "reqtool",
        summary: str = "Updated.", change_ref: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        data = self.requirements.get(uid)
        if data is None:
            return None

        fields = self._sanitise_requirement(fields)
        if fields.get("parentId"):
            if fields["parentId"] != data.get("parentId"):
                self._check_parent_exists(fields["parentId"])
            self._check_parent(uid, fields["parentId"])
        if "id" in fields and fields["id"] != data.get("id"):
            self._check_id(fields["id"], uid)
        if "parentId" in fields or "req_type" in fields:
            self._check_hierarchy(fields.get("req_type", data.get("req_type", "functional")),
                                  fields.get("parentId", data.get("parentId")))
        if "relationships" in fields or "req_type" in fields:
            self._check_relationships(fields.get("req_type", data.get("req_type", "functional")),
                                      fields.get("relationships", data.get("relationships")) or [],
                                      data.get("relationships") or [])
        now = utcnow_iso()
        old_hash = data.get("content_hash", "")

        # Apply updates -- deep merge for known nested blocks so callers can
        # send partial sub-objects (e.g. just approval.approved_by)
        _DEEP_MERGE_KEYS = {"content", "approval", "review", "verification", "implementation"}
        for key, value in fields.items():
            if key in _DEEP_MERGE_KEYS and isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key] = {**data[key], **value}
            else:
                data[key] = value

        new_hash = compute_requirement_hash(data)
        if new_hash != old_hash:
            data["version"] = bump_version(data.get("version", "1.0.0"), increment)
            data["content_hash"] = new_hash
            self._mark_downstream_suspect(uid)

        data["last_modified"] = now
        history = data.get("history", [])
        history = list(history)  # append-only audit trail: never truncate
        history.append({"version": data["version"], "date": now, "modified_by": resolve_author(author),
                        "summary": summary, "commit_sha": None, "change_ref": change_ref})
        data["history"] = history

        save_yaml(self.req_path(uid), data)
        return data

    def hierarchy_problem(self, child_type: str, parent_uid: Optional[str]) -> Optional[str]:
        """Message if ``child_type`` is not allowed under ``parent_uid``'s type (ignores enforce mode)."""
        parent = self.requirements.get(parent_uid) if parent_uid else None
        if not parent:
            return None
        return hierarchy_store.check_parent_type(
            self.hierarchy, parent.get("req_type", "functional"), child_type)

    def _check_hierarchy(self, child_type: str, parent_uid: Optional[str]) -> None:
        if self.hierarchy.enforce != "error":
            return
        problem = self.hierarchy_problem(child_type, parent_uid)
        if problem:
            raise HierarchyViolation(problem)

    def relationship_problem(self, source_type: str, rel: dict) -> Optional[str]:
        """Message if ``rel`` breaks cross_layer_rules for a source of ``source_type`` (ignores enforce)."""
        target = self.requirements.get((rel.get("target") or {}).get("uid", ""))
        if not target or not rel.get("type"):
            return None
        return hierarchy_store.check_relationship(
            self.hierarchy, source_type, target.get("req_type", "functional"), rel["type"])

    def _check_relationships(self, source_type: str, rels: list, existing: list) -> None:
        """Reject relationships that are new (not already stored) and break cross_layer_rules."""
        if self.hierarchy.enforce != "error":
            return
        key = lambda r: (r.get("type"), (r.get("target") or {}).get("uid"))
        have = {key(r) for r in existing}
        for rel in rels:
            if key(rel) in have:
                continue
            problem = self.relationship_problem(source_type, rel)
            if problem:
                raise RelationshipViolation(problem)

    def _check_id(self, rid: Any, own_uid: Optional[str]) -> None:
        """A human ID must be a safe single segment and unused by any other live requirement."""
        validate_id(rid, "requirement id")
        for other_uid, other in self.requirements.items():
            if other_uid != own_uid and not other.get("deleted") and other.get("id") == rid:
                raise DuplicateId(f"ID '{rid}' is already used by another requirement")

    def resolve_uid(self, key: str) -> Optional[str]:
        """Accept a UID or a human ID (unique, non-deleted) and return the UID."""
        if key in self.requirements:
            return key
        hits = [u for u, r in self.requirements.items() if r.get("id") == key and not r.get("deleted")]
        return hits[0] if len(hits) == 1 else None

    def _check_parent_exists(self, parent_uid: Optional[str]) -> None:
        """Raise UnknownParent unless ``parent_uid`` is empty or a live requirement."""
        if not parent_uid:
            return
        parent = self.requirements.get(parent_uid)
        if parent is None or parent.get("deleted"):
            raise UnknownParent(f"parentId '{parent_uid}' is not an existing requirement")

    def _check_parent(self, uid: str, new_parent: str) -> None:
        """Raise ParentCycle if parenting ``uid`` under ``new_parent`` closes a loop."""
        seen: set[str] = set()
        cur: Optional[str] = new_parent
        while cur and cur not in seen:
            if cur == uid:
                raise ParentCycle(
                    "An item cannot be its own parent" if new_parent == uid
                    else f"Parent {new_parent} is a descendant of {uid}; this would create a cycle")
            seen.add(cur)
            cur = (self.requirements.get(cur) or {}).get("parentId")

    def _mark_downstream_suspect(self, upstream_uid: str) -> None:
        """Flag links to ``upstream_uid`` as suspect, and transitively the links to every item flagged.

        Each newly flagged item gets a history entry (no version bump: the content is unchanged).
        A visited set makes loops in the link graph safe.
        """
        dependants: dict[str, list[str]] = {}
        for req_uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            for rel in req.get("relationships") or []:
                target = (rel.get("target") or {}).get("uid") or rel.get("uid")
                if target:
                    dependants.setdefault(target, []).append(req_uid)

        now = utcnow_iso()
        visited = {upstream_uid}
        queue = [upstream_uid]
        while queue:
            current = queue.pop(0)
            current_id = (self.requirements.get(current) or {}).get("id", current)
            for req_uid in dict.fromkeys(dependants.get(current, [])):
                if req_uid == upstream_uid:
                    continue
                req = self.requirements[req_uid]
                newly = False
                for rel in req.get("relationships") or []:
                    if ((rel.get("target") or {}).get("uid") or rel.get("uid")) == current and not rel.get("suspect"):
                        rel["suspect"] = True
                        newly = True
                if newly:
                    history = list(req.get("history") or [])
                    history.append({
                        "version": req.get("version", "1.0.0"), "date": now, "modified_by": resolve_author("reqtool"),
                        "summary": f"Link to {current_id} became suspect (upstream change)",
                        "commit_sha": None, "change_ref": None})
                    req["history"] = history
                    save_yaml(self.req_path(req_uid), req)
                if req_uid not in visited:
                    visited.add(req_uid)
                    queue.append(req_uid)

    @_locked
    def clear_suspect_link(self, req_uid: str, rel_index: int) -> bool:
        """Clear suspect flag on a relationship link."""
        req = self.requirements.get(req_uid)
        if not req or "relationships" not in req:
            return False
        rels = req["relationships"]
        if 0 <= rel_index < len(rels):
            rels[rel_index]["suspect"] = False
            save_yaml(self.req_path(req_uid), req)
            return True
        return False

    @_locked
    def approve_requirement(self, uid: str, approved_by: str, identity_verified: bool = False) -> Optional[dict[str, Any]]:
        """Approve a requirement and sign the approved content (atomic under the store lock)."""
        from .auth import sign_approval_v2
        if uid not in self.requirements:
            return None
        result = self.update_requirement(uid, {
            "approval": {
                "status": "approved",
                "approved_by": approved_by,
                "approved_date": utcnow_iso(),
                "identity_verified": identity_verified,
            },
            "status": "approved",
        }, increment="minor", summary=f"Approved by {approved_by}")
        if result is None:
            return None
        approval = result["approval"]
        approval["signed_version"] = result["version"]
        approval["signed_hash"] = result["content_hash"]
        approval["signature"] = sign_approval_v2(uid, result["version"], approved_by, result["content_hash"], self.root)
        save_yaml(self.req_path(uid), result)
        return result

    @_locked
    def delete_requirement(self, uid: str) -> Optional[dict[str, Any]]:
        data = self.requirements.get(uid)
        if data is None:
            return None
        # Children of a deleted item would vanish from the tree: move them up a level.
        for child_uid, child in list(self.requirements.items()):
            if child.get("parentId") == uid and not child.get("deleted"):
                note = f"Re-parented after {data.get('id', uid)} was deleted"
                try:
                    self.update_requirement(child_uid, {"parentId": data.get("parentId")}, summary=note)
                except (HierarchyViolation, ParentCycle):
                    # The grandparent may not accept this type: fall back to the root.
                    self.update_requirement(child_uid, {"parentId": None}, summary=note)
        data["deleted"] = True
        data["last_modified"] = utcnow_iso()
        save_yaml(self.req_path(uid), data)
        return data

    # ------------------------------------------------------------------
    # Write helpers: principle
    # ------------------------------------------------------------------

    @_locked
    def create_principle(self, fields: dict[str, Any], author: str = "reqtool") -> dict[str, Any]:
        uid = uuid7()
        now = utcnow_iso()
        data: dict[str, Any] = {
            "schema_version": "1.0.0",
            "type": "principle",
            "tool_version": TOOL_VERSION,
            "uid": uid,
            "id": fields.get("id", f"P-{uid[:8]}"),
            "title": fields.get("title", ""),
            "version": "1.0.0",
            "content": fields.get("content", {"description": "", "rationale": "", "implications": "", "exceptions": ""}),
            "domain": fields.get("domain"),
            "tags": fields.get("tags", []),
            "owner": fields.get("owner"),
            "links": fields.get("links", []),
            "attachments": fields.get("attachments", []),
            "status": fields.get("status", "draft"),
            "approval": fields.get("approval", {"status": "draft", "approved_by": None, "approved_date": None}),
            "review": fields.get("review", {"last_reviewed": None, "reviewers": [], "note": ""}),
            "content_hash": "",
            "created": now,
            "last_modified": now,
            "deleted": False,
            "history": [{"version": "1.0.0", "date": now, "modified_by": resolve_author(author),
                         "summary": "Initial draft.", "commit_sha": None, "change_ref": None}],
        }
        data["content_hash"] = compute_principle_hash(data)
        self.principles[uid] = data
        save_yaml(self.principle_path(uid), data)
        return data

    @_locked
    def update_principle(
        self, uid: str, fields: dict[str, Any],
        increment: str = "patch", author: str = "reqtool",
        summary: str = "Updated.", change_ref: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        data = self.principles.get(uid)
        if data is None:
            return None
        now = utcnow_iso()
        old_hash = data.get("content_hash", "")
        for key, value in fields.items():
            data[key] = value
        new_hash = compute_principle_hash(data)
        if new_hash != old_hash:
            data["version"] = bump_version(data.get("version", "1.0.0"), increment)
            data["content_hash"] = new_hash
        data["last_modified"] = now
        history = data.get("history", [])
        history = list(history)  # append-only audit trail: never truncate
        history.append({"version": data["version"], "date": now, "modified_by": resolve_author(author),
                        "summary": summary, "commit_sha": None, "change_ref": change_ref})
        data["history"] = history
        save_yaml(self.principle_path(uid), data)
        return data

    @_locked
    def delete_principle(self, uid: str) -> Optional[dict[str, Any]]:
        data = self.principles.get(uid)
        if data is None:
            return None
        data["deleted"] = True
        data["last_modified"] = utcnow_iso()
        save_yaml(self.principle_path(uid), data)
        return data

    # ------------------------------------------------------------------
    # Write helpers: Decision Record (ADR) & TBD
    # ------------------------------------------------------------------

    @_locked
    def create_decision(self, fields: dict[str, Any], author: str = "reqtool") -> dict[str, Any]:
        uid = uuid7()
        now = utcnow_iso()
        item_type = fields.get("type", "decision")
        prefix = "TBD" if item_type == "tbd" else "DEC"
        default_status = "open" if item_type == "tbd" else "proposed"
        data: dict[str, Any] = {
            "schema_version": "1.0.0",
            "type": item_type,
            "tool_version": TOOL_VERSION,
            "uid": uid,
            "id": fields.get("id", f"{prefix}-{uid[:8]}"),
            "title": fields.get("title", ""),
            "version": "1.0.0",
            "content": fields.get("content", {
                "context": "", "description": "", "impact": "",
                "resolution_criteria": "", "resolution": None,
                "options": [], "chosen_option": None, "rationale": "",
            }),
            "owner": fields.get("owner"),
            "due": fields.get("due"),
            "status": fields.get("status", default_status),
            "priority": fields.get("priority", "medium"),
            "supersedes": fields.get("supersedes"),
            "superseded_by": fields.get("superseded_by"),
            "affected_requirements": fields.get("affected_requirements", []),
            "links": fields.get("links", []),
            "attachments": fields.get("attachments", []),
            "tags": fields.get("tags", []),
            "content_hash": "",
            "created": now,
            "last_modified": now,
            "deleted": False,
            "history": [{"version": "1.0.0", "date": now, "modified_by": resolve_author(author),
                         "summary": "Initial draft.", "commit_sha": None, "change_ref": None}],
        }
        data["content_hash"] = compute_tbd_hash(data)
        self.decisions[uid] = data

        # Lineage: if this decision supersedes an older one, mark the old one as superseded
        if data.get("supersedes"):
            self._mark_superseded(data["supersedes"], uid, author)

        save_yaml(self.decision_path(uid), data)
        return data

    def _mark_superseded(self, old_uid: str, new_uid: str, author: str = "reqtool") -> None:
        """Mark ``old_uid`` as superseded by ``new_uid`` as a normal, audited change (rehash, version, history)."""
        old_item = self.decisions.get(old_uid)
        if not old_item or old_item.get("status") == "superseded" and old_item.get("superseded_by") == new_uid:
            return
        now = utcnow_iso()
        old_item["status"] = "superseded"
        old_item["superseded_by"] = new_uid
        new_hash = compute_tbd_hash(old_item)
        if new_hash != old_item.get("content_hash"):
            old_item["version"] = bump_version(old_item.get("version", "1.0.0"), "patch")
            old_item["content_hash"] = new_hash
        old_item["last_modified"] = now
        old_item["history"] = list(old_item.get("history", [])) + [{
            "version": old_item["version"], "date": now, "modified_by": resolve_author(author),
            "summary": f"Superseded by {self.decisions.get(new_uid, {}).get('id', new_uid)}.",
            "commit_sha": None, "change_ref": None}]
        save_yaml(self.decision_path(old_uid), old_item)

    @_locked
    def create_tbd(self, fields: dict[str, Any], author: str = "reqtool") -> dict[str, Any]:
        f = dict(fields)
        f.setdefault("type", "tbd")
        f.setdefault("status", "open")
        return self.create_decision(f, author=author)

    @_locked
    def update_decision(
        self, uid: str, fields: dict[str, Any],
        increment: str = "patch", author: str = "reqtool",
        summary: str = "Updated.", change_ref: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        data = self.decisions.get(uid)
        if data is None:
            return None
        now = utcnow_iso()
        old_hash = data.get("content_hash", "")
        for key, value in fields.items():
            data[key] = value

        # Lineage check
        if fields.get("supersedes"):
            self._mark_superseded(fields["supersedes"], uid, author)

        new_hash = compute_tbd_hash(data)
        if new_hash != old_hash:
            data["version"] = bump_version(data.get("version", "1.0.0"), increment)
            data["content_hash"] = new_hash
        data["last_modified"] = now
        history = data.get("history", [])
        history = list(history)  # append-only audit trail: never truncate
        history.append({"version": data["version"], "date": now, "modified_by": resolve_author(author),
                        "summary": summary, "commit_sha": None, "change_ref": change_ref})
        data["history"] = history
        save_yaml(self.decision_path(uid), data)
        return data

    @_locked
    def update_tbd(self, uid: str, fields: dict[str, Any], **kwargs) -> Optional[dict[str, Any]]:
        return self.update_decision(uid, fields, **kwargs)

    @_locked
    def delete_decision(self, uid: str) -> Optional[dict[str, Any]]:
        data = self.decisions.get(uid)
        if data is None:
            return None
        data["deleted"] = True
        data["last_modified"] = utcnow_iso()
        save_yaml(self.decision_path(uid), data)
        return data

    @_locked
    def delete_tbd(self, uid: str) -> Optional[dict[str, Any]]:
        return self.delete_decision(uid)

    # ------------------------------------------------------------------
    # Affected requirements for TBDs
    # ------------------------------------------------------------------

    @_locked
    def reload_file(self, changed_path: Path) -> None:
        """Incrementally reload a single changed YAML file instead of full reload.
        Falls back to full reload for config/enums changes.
        """
        with self._lock:
            # Determine collection from path. A path outside this repository (events from a repository
            # that was switched away from) is not ours to handle.
            try:
                rel = changed_path.relative_to(self.root) if changed_path.is_absolute() else changed_path
            except ValueError:
                log.debug("Ignoring change outside the repository: %s", changed_path)
                return
            parts = rel.parts

            # Config or enums changes require full reload
            if parts and parts[0] == ".reqtool":
                log.info("Config file changed, full reload: %s", changed_path)
                self.load()
                return

            if not parts:
                self.load()
                return

            top = parts[0]

        try:
            if top == "requirements":
                if not changed_path.exists():
                    to_remove = [uid for uid, r in self.requirements.items()
                                 if self.req_path(uid) == changed_path]
                    for uid in to_remove:
                        del self.requirements[uid]
                        self._file_for.pop(("requirements", uid), None)
                    log.debug("Incremental reload: removed %d requirement(s)", len(to_remove))
                    return
                data = load_yaml(changed_path)
                if not isinstance(data, dict):
                    return
                uid = data.get("uid")
                if not uid:
                    return
                # Skip only when the file matches memory (our own just-written update). Comparing content,
                # not timestamps, means hand edits and a git checkout of an older version are picked up.
                existing = self.requirements.get(uid)
                if existing == data:
                    log.debug("Incremental reload: in-memory is current for %s, skip", uid)
                    return
                self.requirements[uid] = data
                self._file_for[("requirements", uid)] = changed_path
                log.debug("Incremental reload: requirement %s", uid)
                return

            if top == "principles":
                if not changed_path.exists():
                    to_remove = [uid for uid, p in self.principles.items()
                                 if self.principle_path(uid) == changed_path]
                    for uid in to_remove:
                        del self.principles[uid]
                        self._file_for.pop(("principles", uid), None)
                    return
                data = load_yaml(changed_path)
                if not isinstance(data, dict):
                    return
                uid = data.get("uid")
                if uid:
                    if self.principles.get(uid) == data:
                        return
                    self.principles[uid] = data
                    self._file_for[("principles", uid)] = changed_path
                return

            if top in ("decisions", "tbds"):
                if not changed_path.exists():
                    for uid in [u for u in self.decisions if self.decision_path(u) == changed_path]:
                        del self.decisions[uid]
                        self._file_for.pop(("decisions", uid), None)
                    return
                data = load_yaml(changed_path)
                if isinstance(data, dict) and (uid := data.get("uid")):
                    if self.decisions.get(uid) == data:
                        return
                    self.decisions[uid] = data
                    self._file_for[("decisions", uid)] = changed_path
                return

            if top in ("modules", "products"):
                self._load_modules()
                self._load_products()
                return

        except FileNotFoundError:
            log.debug("Transient file-not-found during reload of %s -- ignoring", changed_path)
            return
        except Exception as exc:
            log.warning("Incremental reload failed for %s: %s -- falling back to full reload", changed_path, exc)

        self.load()

    @_locked
    def restore_requirement(self, uid: str, snapshot: dict[str, Any]) -> None:
        """Put back an earlier copy of a requirement (used when a commit fails after the item was updated)."""
        self.requirements[uid] = snapshot
        save_yaml(self.req_path(uid), snapshot)

    @_locked
    def restore_decision(self, uid: str, snapshot: dict[str, Any]) -> None:
        self.decisions[uid] = snapshot
        save_yaml(self.decision_path(uid), snapshot)

    def live_tbds(self) -> list[dict[str, Any]]:
        """Non-deleted items of type ``tbd`` (open questions), excluding decision records."""
        return [d for d in self.decisions.values() if not d.get("deleted") and d.get("type") == "tbd"]

    def live_decision_records(self) -> list[dict[str, Any]]:
        """Non-deleted decision records (ADRs), excluding TBDs."""
        return [d for d in self.decisions.values() if not d.get("deleted") and d.get("type") != "tbd"]

    def open_tbds_for(self, req: dict[str, Any]) -> list[str]:
        """Ids of unresolved TBDs the requirement links to."""
        out = []
        for link in req.get("links", []) or []:
            if link.get("type") != "tbd":
                continue
            t = self.decisions.get(link.get("ref", ""))
            if t and not t.get("deleted") and t.get("type") == "tbd" and t.get("status") in ("open", "in_progress"):
                out.append(t.get("id") or t["uid"])
        return out

    def compute_affected_requirements(self, tbd_uid: str) -> list[str]:
        """Return UIDs of live requirements that reference ``tbd_uid``.

        A requirement is affected if it has a ``tbd`` link whose ``ref`` is the
        UID, or a relationship that points at it via ``target.uid``, ``uid`` or
        ``ref``. (Also used for decisions, which are referenced the same way.)
        """
        affected = []
        for uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            hit = False
            for link in req.get("links") or []:
                if link.get("type") == "tbd" and link.get("ref") == tbd_uid:
                    hit = True
                    break
            if not hit:
                for rel in req.get("relationships") or []:
                    tgt = rel.get("target")
                    if (isinstance(tgt, dict) and tgt.get("uid") == tbd_uid) \
                            or rel.get("uid") == tbd_uid or rel.get("ref") == tbd_uid:
                        hit = True
                        break
            if hit:
                affected.append(uid)
        return affected

    # ------------------------------------------------------------------
    # Attachments  (files stored in attachments/<uid>/<filename>)
    # ------------------------------------------------------------------

    def attachment_dir(self, uid: str) -> Path:
        return attachment_store.attachment_dir(self.root, uid)

    def _get_artefact(self, uid: str) -> Optional[tuple[dict, str]]:
        """Return (artefact_dict, type) for any uid, or None."""
        if uid in self.requirements:
            return self.requirements[uid], "requirement"
        if uid in self.principles:
            return self.principles[uid], "principle"
        if uid in self.decisions:
            return self.decisions[uid], "tbd"
        return None

    def _update_artefact(self, uid: str, fields: dict, summary: str) -> Optional[dict]:
        """Update any artefact by uid."""
        if uid in self.requirements:
            return self.update_requirement(uid, fields, summary=summary, increment="patch")
        if uid in self.principles:
            return self.update_principle(uid, fields, summary=summary, increment="patch")
        if uid in self.decisions:
            return self.update_tbd(uid, fields, summary=summary, increment="patch")
        return None

    def add_attachment(
        self, uid: str, filename: str, data: bytes, author: str = "reqtool",
        description: str = "",
    ) -> dict[str, Any]:
        return attachment_store.add_attachment(self, uid, filename, data, resolve_author(author), description)

    def delete_attachment(self, uid: str, filename: str) -> bool:
        return attachment_store.delete_attachment(self, uid, filename)

    def list_attachments(self, uid: str) -> list[dict]:
        return attachment_store.list_attachments(self, uid)

    # ------------------------------------------------------------------
    # Comments  (stored in comments/<uid>.yaml, outside content hash)
    # ------------------------------------------------------------------

    def comments_path(self, uid: str) -> Path:
        return comment_store.comments_path(self.root, uid)

    def get_comments(self, uid: str) -> list[dict[str, Any]]:
        return comment_store.get_comments(self.root, uid)

    def add_comment(
        self, uid: str, text: str, author: str,
        reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        return comment_store.add_comment(self.root, uid, text, resolve_author(author), reply_to)

    def update_comment(self, uid: str, comment_uid: str, text: str) -> Optional[dict[str, Any]]:
        return comment_store.update_comment(self.root, uid, comment_uid, text)

    def resolve_comment(self, uid: str, comment_uid: str, resolved: bool = True) -> Optional[dict[str, Any]]:
        return comment_store.resolve_comment(self.root, uid, comment_uid, resolved)

    def delete_comment(self, uid: str, comment_uid: str) -> bool:
        return comment_store.delete_comment(self.root, uid, comment_uid)

    # ------------------------------------------------------------------
    # Custom field schema (from .reqtool/custom_fields.yaml)
    # ------------------------------------------------------------------

    def load_custom_field_schema(self) -> list[dict[str, Any]]:
        path = self.root / ".reqtool" / "custom_fields.yaml"
        if not path.exists():
            return []
        data = load_yaml(path)
        return data if isinstance(data, list) else []

    def save_custom_field_schema(self, schema: list[dict[str, Any]]) -> None:
        path = self.root / ".reqtool" / "custom_fields.yaml"
        save_yaml(path, schema)

    def validate_custom_fields(self, req: dict[str, Any]) -> list[dict[str, str]]:
        """Validate custom_fields against the project schema. Returns list of errors."""
        schema = self.load_custom_field_schema()
        if not schema:
            return []
        custom = req.get("custom_fields", {})
        errors = []
        for field_def in schema:
            key = field_def.get("key", "")
            if not key:
                continue
            required = field_def.get("required", False)
            field_type = field_def.get("type", "string")
            options = field_def.get("options", [])
            val = custom.get(key)

            if required and (val is None or val == ""):
                errors.append({"field": f"custom_fields.{key}", "message": f"Required custom field '{key}' is missing"})
                continue

            if val is None:
                continue

            if field_type == "number":
                try:
                    float(str(val))
                except ValueError:
                    errors.append({"field": f"custom_fields.{key}", "message": f"Custom field '{key}' must be a number"})

            if options and str(val) not in [str(o) for o in options]:
                errors.append({"field": f"custom_fields.{key}", "message": f"Custom field '{key}' value '{val}' not in allowed options"})

        return errors

    # ------------------------------------------------------------------
    # Hierarchy helpers
    # ------------------------------------------------------------------

    def get_workflow_for_type(self, req_type: str) -> Optional[HierarchyWorkflowDef]:
        return hierarchy_store.get_workflow_for_type(self.hierarchy, req_type)

    def get_allowed_children(self, req_type: str) -> list[str]:
        return hierarchy_store.get_allowed_children(self.hierarchy, req_type)

    def check_transition_guard(
        self, req: dict[str, Any], to_state: str
    ) -> Optional[str]:
        return hierarchy_store.check_transition_guard(self.hierarchy, req, to_state, self.requirements)

    def validate_transition(
        self, req: dict[str, Any], to_state: str
    ) -> Optional[str]:
        return hierarchy_store.validate_transition(self.hierarchy, self.config.workflow, req, to_state, self.requirements)

    @_locked
    def next_id_for_type(self, req_type: str) -> str:
        return hierarchy_store.next_id_for_type(self.hierarchy, self.requirements, req_type)

    def default_checklist(self, kind: str, req_type: str) -> list[dict[str, Any]]:
        return hierarchy_store.default_checklist(self.hierarchy, kind, req_type)

    # ------------------------------------------------------------------
    # Impact analysis
    # ------------------------------------------------------------------

    IMPACT_REL_TYPES = {"derived_from", "depends_on", "implements", "satisfies"}

    def compute_impact(self, uid: str) -> dict[str, Any]:
        """
        Return the transitive downstream impact closure for a requirement.
        Downstream: items that depend on / are derived from / implement / satisfy `uid`.
        Upstream: items that `uid` depends on / is derived from.
        """
        # Build reverse index: target_uid -> list of (source_uid, rel_type)
        downstream_map: dict[str, list[dict]] = {}
        upstream_map: dict[str, list[dict]] = {}
        for src_uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            for rel in req.get("relationships", []):
                tgt = rel.get("target", {}).get("uid") or rel.get("target", "")
                rel_type = rel.get("type", "")
                if tgt:
                    downstream_map.setdefault(tgt, []).append({
                        "uid": src_uid,
                        "id": req.get("id", ""),
                        "title": req.get("title", ""),
                        "status": req.get("status", ""),
                        "req_type": req.get("req_type", ""),
                        "rel_type": rel_type,
                    })
                    if rel_type in self.IMPACT_REL_TYPES:
                        upstream_map.setdefault(src_uid, []).append({
                            "uid": tgt,
                            "rel_type": rel_type,
                        })

        # BFS downstream closure
        visited: set[str] = set()
        queue = [uid]
        downstream: list[dict] = []
        while queue:
            current = queue.pop(0)
            for item in downstream_map.get(current, []):
                dep_uid = item["uid"]
                if dep_uid not in visited and dep_uid != uid:
                    if item.get("rel_type", "") in self.IMPACT_REL_TYPES:
                        visited.add(dep_uid)
                        downstream.append(item)
                        queue.append(dep_uid)

        # Direct upstream (not transitive for brevity)
        req = self.requirements.get(uid, {})
        upstream: list[dict] = []
        for rel in req.get("relationships", []):
            tgt = rel.get("target", {}).get("uid") or rel.get("target", "")
            if tgt and rel.get("type", "") in self.IMPACT_REL_TYPES:
                tgt_req = self.requirements.get(tgt, {})
                upstream.append({
                    "uid": tgt,
                    "id": tgt_req.get("id", ""),
                    "title": tgt_req.get("title", ""),
                    "status": tgt_req.get("status", ""),
                    "req_type": tgt_req.get("req_type", ""),
                    "rel_type": rel.get("type", ""),
                })

        # Group downstream by type
        by_type: dict[str, list[dict]] = {}
        for item in downstream:
            by_type.setdefault(item.get("req_type", "unknown"), []).append(item)

        return {
            "uid": uid,
            "downstream_count": len(downstream),
            "downstream_by_type": by_type,
            "upstream": upstream,
        }

    # ------------------------------------------------------------------
    # Estimate rollup
    # ------------------------------------------------------------------

    def _live_descendants(self, uid: str) -> list[dict[str, Any]]:
        """All non-deleted descendants of ``uid`` (cycle-safe), excluding ``uid`` itself."""
        kids: dict[str, list[str]] = {}
        for r_uid, r in self.requirements.items():
            if not r.get("deleted") and r.get("parentId"):
                kids.setdefault(r["parentId"], []).append(r_uid)
        seen = {uid}
        out: list[dict[str, Any]] = []
        stack = list(kids.get(uid, []))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            out.append(self.requirements[cur])
            stack.extend(kids.get(cur, []))
        return out

    def _rollup_leaves(self, uid: str) -> list[dict[str, Any]]:
        """Descendants of ``uid`` that have no live children of their own (cancelled items excluded)."""
        desc = self._live_descendants(uid)
        parents = {r.get("parentId") for r in desc}
        return [r for r in desc if r.get("uid") not in parents and r.get("status") != "cancelled"]

    def compute_estimate_rollup(self, uid: str) -> Optional[float]:
        """Sum of the estimates of all leaf descendants (a parent's own estimate is never double counted).

        None if there are no descendants or none of the leaves has an estimate.
        """
        estimates = [r["estimate"] for r in self._rollup_leaves(uid) if r.get("estimate") is not None]
        return sum(estimates) if estimates else None

    # ------------------------------------------------------------------
    # Kanban
    # ------------------------------------------------------------------

    def build_kanban(
        self,
        req_type: Optional[str] = None,
        iteration: Optional[str] = None,
        owner: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Return a column-per-state kanban board.
        Cards contain: uid, id, title, assignee, estimate, priority, req_type.
        """
        # Determine which workflow to show
        if req_type:
            wf = self.get_workflow_for_type(req_type)
        else:
            wf = None

        if wf:
            states = [s.id for s in wf.states]
        else:
            # Fall back to config workflow
            states = [s.id for s in self.config.workflow.states]

        columns: dict[str, list[dict]] = {s: [] for s in states}
        columns["_uncolumned"] = []

        for uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            if req_type and req.get("req_type") != req_type:
                continue
            if iteration and req.get("iteration") != iteration:
                continue
            if owner and req.get("owner") != owner:
                continue
            if assignee and req.get("assignee") != assignee:
                continue

            card = {
                "uid": uid,
                "id": req.get("id", ""),
                "title": req.get("title", ""),
                "assignee": req.get("assignee"),
                "owner": req.get("owner"),
                "estimate": req.get("estimate"),
                "priority": req.get("priority", "medium"),
                "req_type": req.get("req_type", "functional"),
                "iteration": req.get("iteration"),
            }
            status = req.get("status", "draft")
            if status in columns:
                columns[status].append(card)
            else:
                columns["_uncolumned"].append(card)

        if not columns["_uncolumned"]:
            del columns["_uncolumned"]

        return {
            "states": states,
            "columns": columns,
            "req_type": req_type,
        }

    # ------------------------------------------------------------------
    # Filter presets
    # ------------------------------------------------------------------

    def _presets_path(self) -> Path:
        return self.root / ".reqtool" / "filter_presets.yaml"

    def list_filter_presets(self) -> list[dict[str, Any]]:
        path = self._presets_path()
        if not path.exists():
            return []
        data = load_yaml(path)
        return data if isinstance(data, list) else []

    def save_filter_preset(self, preset: dict[str, Any]) -> dict[str, Any]:
        path = self._presets_path()
        presets = self.list_filter_presets()
        presets = [p for p in presets if p.get("id") != preset.get("id")]
        presets.append(preset)
        save_yaml(path, presets)
        return preset

    def delete_filter_preset(self, preset_id: str) -> bool:
        path = self._presets_path()
        presets = self.list_filter_presets()
        new = [p for p in presets if p.get("id") != preset_id]
        if len(new) == len(presets):
            return False
        save_yaml(path, new)
        return True

    @_locked
    def import_module(
        self,
        product_id: str,
        module_id: str,
        locked_by: str = "reqtool",
    ) -> dict[str, Any]:
        """
        Generate / update the lock entry for a module in a product.
        Writes _product.lock alongside _product.yaml.
        Returns the lock dict.
        """
        import hashlib
        from .git_ops import _run_git

        if product_id not in self.products:
            raise ValueError(f"Product '{product_id}' not found")
        if module_id not in self.modules:
            raise ValueError(f"Module '{module_id}' not found")

        module_dir = self.root / "modules" / validate_id(module_id, "module id")
        module_files = sorted(p for p in module_dir.glob("*.yaml") if not p.name.startswith("_"))
        h = hashlib.sha256()
        for f in module_files:
            h.update(f.read_bytes())
        content_hash = f"sha256:{h.hexdigest()}"

        # Try to get the current git SHA
        rc, sha, _ = _run_git(["rev-parse", "HEAD"], self.root)
        commit_sha = sha[:40] if rc == 0 else ""

        module_manifest = self.modules[module_id]
        version = module_manifest.get("version", "1.0.0")
        ref = f"modules/{module_id}/v{version}"

        now = utcnow_iso()
        lock_entry = {
            "id": module_id,
            "version": version,
            "ref": ref,
            "sha": commit_sha,
            "content_hash": content_hash,
            "locked_at": now,
            "locked_by": locked_by,
        }

        lock_path = self.root / "products" / validate_id(product_id, "product id") / "_product.lock"
        if lock_path.exists():
            try:
                existing = load_yaml(lock_path)
                locked_list = existing.get("locked", [])
            except Exception:
                locked_list = []
        else:
            locked_list = []

        # Replace or add entry
        locked_list = [e for e in locked_list if e.get("id") != module_id]
        locked_list.append(lock_entry)

        lock_data = {
            "schema_version": "1.0.0",
            "generated_at": now,
            "generated_by": locked_by,
            "locked": locked_list,
        }
        save_yaml(lock_path, lock_data)
        log.info("Lock written: %s (module %s)", lock_path, module_id)
        return lock_data

    def verify_module(self, product_id: str, module_id: str) -> dict[str, Any]:
        """Verify module files against the lock. Returns {verified, mismatch}."""
        import hashlib
        validate_id(module_id, "module id")
        lock_path = self.root / "products" / validate_id(product_id, "product id") / "_product.lock"
        if not lock_path.exists():
            return {"verified": False, "reason": "lock file missing"}
        try:
            lock = load_yaml(lock_path)
        except Exception as e:
            return {"verified": False, "reason": f"lock parse error: {e}"}

        locked = next((m for m in lock.get("locked", []) if m.get("id") == module_id), None)
        if not locked:
            return {"verified": False, "reason": f"module '{module_id}' not in lock"}

        module_dir = self.root / "modules" / validate_id(module_id, "module id")
        files = sorted(p for p in module_dir.glob("*.yaml") if not p.name.startswith("_"))
        h = hashlib.sha256()
        for f in files:
            h.update(f.read_bytes())
        computed = f"sha256:{h.hexdigest()}"

        if computed == locked.get("content_hash", ""):
            return {"verified": True, "module_id": module_id, "content_hash": computed}
        return {
            "verified": False,
            "reason": "content hash mismatch -- module files have changed since lock was generated",
            "stored": locked.get("content_hash"),
            "computed": computed,
        }

    # ------------------------------------------------------------------
    # UID search (for relationships editor)
    # ------------------------------------------------------------------

    def _done_states(self, req_type: str) -> set[str]:
        """Terminal workflow states other than ``cancelled`` for the type (falls back to the global workflow)."""
        wf = self.get_workflow_for_type(req_type)
        states = wf.states if wf and wf.states else self.config.workflow.states
        return {s.id for s in states if s.terminal and s.id != "cancelled"}

    def compute_progress_rollup(self, uid: str) -> dict[str, Any]:
        """Progress of ``uid`` over its leaf descendants.

        An item is done when it is in a terminal state of its own workflow (``cancelled`` is not
        completion and is left out of the totals). The root is excluded; ``active`` is not done.
        With no descendants the item's own state decides.
        """
        target = self.requirements.get(uid)
        if not target:
            return {"uid": uid, "total_items": 0, "done_items": 0, "total_estimate": 0.0, "done_estimate": 0.0, "progress_pct": 0.0}

        items = self._rollup_leaves(uid)
        if not items and target.get("status") != "cancelled":
            items = [target]

        total_estimate = done_estimate = 0.0
        done_items = 0
        done_cache: dict[str, set[str]] = {}
        for item in items:
            est = float(item.get("estimate") or 0.0)
            rt = item.get("req_type", "")
            if rt not in done_cache:
                done_cache[rt] = self._done_states(rt)
            total_estimate += est
            if item.get("status") in done_cache[rt]:
                done_items += 1
                done_estimate += est

        total_items = len(items)
        pct = round(done_estimate / total_estimate * 100.0, 1) if total_estimate > 0 else (
            round(done_items / total_items * 100.0, 1) if total_items else 0.0)
        return {
            "uid": uid,
            "id": target.get("id", ""),
            "title": target.get("title", ""),
            "total_items": total_items,
            "done_items": done_items,
            "total_estimate": total_estimate,
            "done_estimate": done_estimate,
            "progress_pct": pct,
        }

    def search_uids(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search requirements, principles, and TBDs by ID or title fragment."""
        q = query.lower().strip()
        results = []
        for uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            if q in req.get("id", "").lower() or q in req.get("title", "").lower():
                results.append({
                    "uid": uid,
                    "id": req.get("id", ""),
                    "title": req.get("title", ""),
                    "type": "requirement",
                })
        for uid, p in self.principles.items():
            if p.get("deleted"):
                continue
            if q in p.get("id", "").lower() or q in p.get("title", "").lower():
                results.append({
                    "uid": uid,
                    "id": p.get("id", ""),
                    "title": p.get("title", ""),
                    "type": "principle",
                })
        for uid, d in self.decisions.items():
            if d.get("deleted"):
                continue
            if q in d.get("id", "").lower() or q in d.get("title", "").lower():
                results.append({
                    "uid": uid,
                    "id": d.get("id", ""),
                    "title": d.get("title", ""),
                    "type": "tbd" if d.get("type") == "tbd" else "decision",
                })
        return results[:limit]

    def fetch_remote_module(self, module_id: str) -> dict[str, Any]:
        """Fetch an external Git repository module into modules/<module_id>/."""
        validate_id(module_id, "module id")

        manifest_path = self.root / "modules" / module_id / "_module.yaml"
        if not manifest_path.exists():
            raise ValueError(f"Module manifest for '{module_id}' not found")
        data = load_yaml(manifest_path)
        git_remote = str(data.get("git_remote", "")).strip()
        git_ref = str(data.get("git_ref", "main")).strip()
        if not git_remote:
            raise ValueError(f"Module '{module_id}' does not specify 'git_remote'")

        _validate_remote_url(git_remote)
        _validate_remote_ref(git_ref)

        target_dir = self.root / "modules" / module_id / "remote"
        target_dir.mkdir(parents=True, exist_ok=True)
        if (target_dir / ".git").exists():
            _git_remote(["fetch", "origin"], target_dir)
            _git_remote(["checkout", git_ref, "--"], target_dir)
        else:
            _git_remote(["clone", "--branch", git_ref, "--", git_remote, str(target_dir)], self.root)

        self._load_modules()
        return {"status": "fetched", "module_id": module_id, "git_remote": git_remote, "git_ref": git_ref}

