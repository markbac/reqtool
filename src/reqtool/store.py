"""
reqtool.store
=============
In-memory graph of all artefacts loaded from the repository.
Provides lookup by UID, tree construction, validation, and mutation helpers.
"""

from __future__ import annotations

import logging
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


class Store:
    """
    Holds all loaded artefacts in memory.
    Call load() to populate from disk.
    """

    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root
        self.config: RepoConfig = RepoConfig()
        self.core_enums: CoreEnums = CoreEnums()
        self.repo_enums: RepoEnums = RepoEnums()
        self.hierarchy: HierarchyConfig = HierarchyConfig()

        self.requirements: dict[str, dict[str, Any]] = {}
        self.principles: dict[str, dict[str, Any]] = {}
        self.tbds: dict[str, dict[str, Any]] = {}
        self.modules: dict[str, dict[str, Any]] = {}
        self.products: dict[str, dict[str, Any]] = {}
        self.module_requirements: dict[str, dict[str, dict[str, Any]]] = {}
        # module_requirements[module_id][uid] = req dict

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load (or reload) all artefacts from the repository root."""
        # Reset all collections to prevent stale data from deleted files
        self.requirements = {}
        self.principles = {}
        self.tbds = {}
        self.modules = {}
        self.products = {}
        self.module_requirements = {}

        self._load_config()
        self._load_enums()
        self._load_hierarchy()
        self._load_dir(self.root / "requirements", self.requirements)
        self._load_dir(self.root / "principles", self.principles)
        self._load_dir(self.root / "tbds", self.tbds)
        self._load_modules()
        self._load_products()
        log.info(
            "Store loaded: %d requirements, %d principles, %d TBDs, "
            "%d modules, %d products",
            len(self.requirements), len(self.principles), len(self.tbds),
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
        project_path = self.root / ".reqtool" / "hierarchy.yaml"
        default_path = Path(__file__).parent / "defaults" / "hierarchy.yaml"
        for path in (project_path, default_path):
            if path.exists():
                try:
                    data = load_yaml(path)
                    if isinstance(data, dict):
                        # Parse workflows with guards (not natively handled by simple model_validate)
                        self.hierarchy = self._parse_hierarchy(data)
                        return
                except Exception as exc:
                    log.warning("Failed to load hierarchy from %s: %s", path, exc)
        # Leave default empty HierarchyConfig if nothing loads
        log.debug("No hierarchy.yaml found; using empty HierarchyConfig")

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
            cross_layer_rules=cross_layer,
            default_relationship_types=rel_types,
        )

    def _load_dir(self, directory: Path, target: dict) -> None:
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            try:
                data = load_yaml(path)
                uid = data.get("uid")
                if uid:
                    target[uid] = data
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
        uids.update(self.tbds)
        for reqs in self.module_requirements.values():
            uids.update(reqs)
        return uids

    def get_requirement(self, uid: str) -> Optional[dict]:
        return self.requirements.get(uid)

    def get_principle(self, uid: str) -> Optional[dict]:
        return self.principles.get(uid)

    def get_tbd(self, uid: str) -> Optional[dict]:
        return self.tbds.get(uid)

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
        return self.root / "requirements" / f"{uid}.yaml"

    def principle_path(self, uid: str) -> Path:
        return self.root / "principles" / f"{uid}.yaml"

    def tbd_path(self, uid: str) -> Path:
        return self.root / "tbds" / f"{uid}.yaml"

    # ------------------------------------------------------------------
    # Tree construction
    # ------------------------------------------------------------------

    def build_tree(self, product_id: Optional[str] = None, variant: Optional[str] = None) -> list[dict]:
        """
        Return a nested tree for the given product.
        Each node: {uid, id, title, status, type, children: [...]}
        """
        all_reqs = dict(self.requirements)

        # Include module requirements for this product, applying overrides
        if product_id and product_id in self.products:
            product = self.products[product_id]
            for mod_ref in product.get("modules", []):
                mod_id = mod_ref.get("id")
                overrides = mod_ref.get("overrides", {}) or {}
                module = self.modules.get(mod_id, {})
                overrideable: set[str] = set(module.get("overrideable", []))

                if mod_id in self.module_requirements:
                    for uid, req in self.module_requirements[mod_id].items():
                        if uid not in all_reqs:
                            merged = {**req, "_module": mod_id}
                            # Apply per-UID overrides from product manifest
                            if uid in overrides:
                                uid_overrides = overrides[uid]
                                for field, value in uid_overrides.items():
                                    if field in overrideable:
                                        # Handle nested fields like attributes.*
                                        if "." in field:
                                            top, sub = field.split(".", 1)
                                            if isinstance(merged.get(top), dict):
                                                merged[top] = {**merged[top], sub: value}
                                        else:
                                            merged[field] = value
                                    # silently ignore non-overrideable fields per spec
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

        def node(req: dict) -> dict:
            uid = req["uid"]
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
                "children": [node(c) for c in sorted(
                    children_map.get(uid, []),
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

    def create_requirement(self, fields: dict[str, Any], author: str = "reqtool") -> dict[str, Any]:
        fields = self._sanitise_requirement(fields)
        uid = uuid7()
        now = utcnow_iso()
        req_type = fields.get("req_type", "functional")

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
            "verification_method": fields.get("verification_method", "test"),
            "verification": fields.get("verification", {"status": "not_started", "verified_date": None, "note": ""}),
            "approval": fields.get("approval", {"status": "draft", "approved_by": None, "approved_date": None}),
            "review": fields.get("review", {"last_reviewed": None, "reviewers": [], "note": ""}),
            "implementation": fields.get("implementation", {"status": "not_started", "branch": None}),
            "content_hash": "",
            "created": now,
            "last_modified": now,
            "deleted": False,
            "history": [{"version": "1.0.0", "date": now, "modified_by": author,
                         "summary": "Initial draft.", "commit_sha": None, "change_ref": None}],
        }
        data["content_hash"] = compute_requirement_hash(data)
        self.requirements[uid] = data
        save_yaml(self.req_path(uid), data)
        return data

    def update_requirement(
        self, uid: str, fields: dict[str, Any],
        increment: str = "patch", author: str = "reqtool",
        summary: str = "Updated.", change_ref: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        data = self.requirements.get(uid)
        if data is None:
            return None

        fields = self._sanitise_requirement(fields)
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

        data["last_modified"] = now
        history = data.get("history", [])
        history = history[-19:]  # Keep max 19 + this new entry = 20
        history.append({"version": data["version"], "date": now, "modified_by": author,
                        "summary": summary, "commit_sha": None, "change_ref": change_ref})
        data["history"] = history

        save_yaml(self.req_path(uid), data)
        return data

    def delete_requirement(self, uid: str) -> Optional[dict[str, Any]]:
        data = self.requirements.get(uid)
        if data is None:
            return None
        data["deleted"] = True
        data["last_modified"] = utcnow_iso()
        save_yaml(self.req_path(uid), data)
        return data

    # ------------------------------------------------------------------
    # Write helpers: principle
    # ------------------------------------------------------------------

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
            "history": [{"version": "1.0.0", "date": now, "modified_by": author,
                         "summary": "Initial draft.", "commit_sha": None, "change_ref": None}],
        }
        data["content_hash"] = compute_principle_hash(data)
        self.principles[uid] = data
        save_yaml(self.principle_path(uid), data)
        return data

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
        history = history[-19:]
        history.append({"version": data["version"], "date": now, "modified_by": author,
                        "summary": summary, "commit_sha": None, "change_ref": change_ref})
        data["history"] = history
        save_yaml(self.principle_path(uid), data)
        return data

    def delete_principle(self, uid: str) -> Optional[dict[str, Any]]:
        data = self.principles.get(uid)
        if data is None:
            return None
        data["deleted"] = True
        data["last_modified"] = utcnow_iso()
        save_yaml(self.principle_path(uid), data)
        return data

    # ------------------------------------------------------------------
    # Write helpers: TBD
    # ------------------------------------------------------------------

    def create_tbd(self, fields: dict[str, Any], author: str = "reqtool") -> dict[str, Any]:
        uid = uuid7()
        now = utcnow_iso()
        data: dict[str, Any] = {
            "schema_version": "1.0.0",
            "type": "tbd",
            "tool_version": TOOL_VERSION,
            "uid": uid,
            "id": fields.get("id", f"TBD-{uid[:8]}"),
            "title": fields.get("title", ""),
            "version": "1.0.0",
            "content": fields.get("content", {"description": "", "impact": "", "resolution_criteria": "", "resolution": None}),
            "owner": fields.get("owner"),
            "due": fields.get("due"),
            "status": fields.get("status", "open"),
            "priority": fields.get("priority", "medium"),
            "affected_requirements": fields.get("affected_requirements", []),
            "links": fields.get("links", []),
            "attachments": fields.get("attachments", []),
            "tags": fields.get("tags", []),
            "content_hash": "",
            "created": now,
            "last_modified": now,
            "deleted": False,
            "history": [{"version": "1.0.0", "date": now, "modified_by": author,
                         "summary": "Initial draft.", "commit_sha": None, "change_ref": None}],
        }
        data["content_hash"] = compute_tbd_hash(data)
        self.tbds[uid] = data
        save_yaml(self.tbd_path(uid), data)
        return data

    def update_tbd(
        self, uid: str, fields: dict[str, Any],
        increment: str = "patch", author: str = "reqtool",
        summary: str = "Updated.", change_ref: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        data = self.tbds.get(uid)
        if data is None:
            return None
        now = utcnow_iso()
        old_hash = data.get("content_hash", "")
        for key, value in fields.items():
            data[key] = value
        new_hash = compute_tbd_hash(data)
        if new_hash != old_hash:
            data["version"] = bump_version(data.get("version", "1.0.0"), increment)
            data["content_hash"] = new_hash
        data["last_modified"] = now
        history = data.get("history", [])
        history = history[-19:]
        history.append({"version": data["version"], "date": now, "modified_by": author,
                        "summary": summary, "commit_sha": None, "change_ref": change_ref})
        data["history"] = history
        save_yaml(self.tbd_path(uid), data)
        return data

    def delete_tbd(self, uid: str) -> Optional[dict[str, Any]]:
        data = self.tbds.get(uid)
        if data is None:
            return None
        data["deleted"] = True
        data["last_modified"] = utcnow_iso()
        save_yaml(self.tbd_path(uid), data)
        return data

    # ------------------------------------------------------------------
    # Affected requirements for TBDs
    # ------------------------------------------------------------------

    def reload_file(self, changed_path: Path) -> None:
        """Incrementally reload a single changed YAML file instead of full reload.
        Falls back to full reload for config/enums changes.
        """
        path_str = str(changed_path)

        # Config or enums changes require full reload
        if ".reqtool" in path_str:
            log.info("Config file changed, full reload: %s", changed_path)
            self.load()
            return

        # Determine collection from path
        rel = changed_path.relative_to(self.root) if changed_path.is_absolute() else changed_path
        parts = rel.parts

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
                    log.debug("Incremental reload: removed %d requirement(s)", len(to_remove))
                    return
                data = load_yaml(changed_path)
                if not isinstance(data, dict):
                    return
                uid = data.get("uid")
                if not uid:
                    return
                # Skip if in-memory copy is already at same or newer version
                # (prevents watchdog from overwriting our own just-written update)
                existing = self.requirements.get(uid)
                if existing and existing.get("last_modified", "") >= data.get("last_modified", ""):
                    log.debug("Incremental reload: in-memory is current for %s, skip", uid)
                    return
                self.requirements[uid] = data
                log.debug("Incremental reload: requirement %s", uid)
                return

            if top == "principles":
                if not changed_path.exists():
                    to_remove = [uid for uid, p in self.principles.items()
                                 if self.principle_path(uid) == changed_path]
                    for uid in to_remove:
                        del self.principles[uid]
                    return
                data = load_yaml(changed_path)
                if not isinstance(data, dict):
                    return
                uid = data.get("uid")
                if uid:
                    existing = self.principles.get(uid)
                    if existing and existing.get("last_modified", "") >= data.get("last_modified", ""):
                        return
                    self.principles[uid] = data
                return

            if top == "tbds":
                if not changed_path.exists():
                    return
                data = load_yaml(changed_path)
                if isinstance(data, dict) and (uid := data.get("uid")):
                    existing = self.tbds.get(uid)
                    if existing and existing.get("last_modified", "") >= data.get("last_modified", ""):
                        return
                    self.tbds[uid] = data
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

    def compute_affected_requirements(self, tbd_uid: str) -> list[str]:
        """Return UIDs of requirements that reference this TBD in their links or relationships."""
        affected = []
        for uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            for link in req.get("links", []):
                if link.get("type") == "tbd" and link.get("ref") == tbd_uid:
                    affected.append(uid)
                    break
            else:
                for rel in req.get("relationships", []):
                    tgt = rel.get("target", {})
                    if isinstance(tgt, dict) and tgt.get("uid") == tbd_uid:
                        affected.append(uid)
                        break
        return affected

    # ------------------------------------------------------------------
    # Attachments  (files stored in attachments/<uid>/<filename>)
    # ------------------------------------------------------------------

    def attachment_dir(self, uid: str) -> Path:
        return self.root / "attachments" / uid

    def _get_artefact(self, uid: str) -> Optional[tuple[dict, str]]:
        """Return (artefact_dict, type) for any uid, or None."""
        if uid in self.requirements:
            return self.requirements[uid], "requirement"
        if uid in self.principles:
            return self.principles[uid], "principle"
        if uid in self.tbds:
            return self.tbds[uid], "tbd"
        return None

    def _update_artefact(self, uid: str, fields: dict, summary: str) -> Optional[dict]:
        """Update any artefact by uid."""
        if uid in self.requirements:
            return self.update_requirement(uid, fields, summary=summary, increment="patch")
        if uid in self.principles:
            return self.update_principle(uid, fields, summary=summary, increment="patch")
        if uid in self.tbds:
            return self.update_tbd(uid, fields, summary=summary, increment="patch")
        return None

    def add_attachment(
        self, uid: str, filename: str, data: bytes, author: str = "reqtool",
        description: str = "",
    ) -> dict[str, Any]:
        """Save a file and record it in the artefact's attachments list.

        Works for requirements, principles, and TBDs.
        Order: update YAML first, then write binary.
        """
        import hashlib
        dest_dir = self.attachment_dir(uid)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename

        sha256 = f"sha256:{hashlib.sha256(data).hexdigest()}"
        now = utcnow_iso()
        record = {
            "filename": filename,
            "size_bytes": len(data),
            "sha256": sha256,
            "added_by": author,
            "added_at": now,
            "description": description,
        }

        result = self._get_artefact(uid)
        if result is None:
            raise ValueError(f"Artefact {uid} not found")
        artefact, _ = result
        attachments = list(artefact.get("attachments", []))
        attachments = [a for a in attachments if a.get("filename") != filename]
        attachments.append(record)

        # Update YAML first -- watchdog will see the updated record
        self._update_artefact(uid, {"attachments": attachments},
                              summary=f"Added attachment: {filename}")

        # Write binary after YAML is stable
        dest.write_bytes(data)
        return record

    def delete_attachment(self, uid: str, filename: str) -> bool:
        dest = self.attachment_dir(uid) / filename
        if dest.exists():
            dest.unlink()
        result = self._get_artefact(uid)
        if result is None:
            return False
        artefact, _ = result
        before = artefact.get("attachments", [])
        after = [a for a in before if a.get("filename") != filename]
        if len(after) == len(before) and not dest.exists():
            # Nothing was removed
            return False
        self._update_artefact(uid, {"attachments": after},
                              summary=f"Removed attachment: {filename}")
        return True

    def list_attachments(self, uid: str) -> list[dict]:
        result = self._get_artefact(uid)
        if result is None:
            return []
        artefact, _ = result
        return artefact.get("attachments", [])

    # ------------------------------------------------------------------
    # Comments  (stored in comments/<uid>.yaml, outside content hash)
    # Works for requirements, principles, and TBDs.
    # ------------------------------------------------------------------

    def comments_path(self, uid: str) -> Path:
        return self.root / "comments" / f"{uid}.yaml"

    def get_comments(self, uid: str) -> list[dict[str, Any]]:
        path = self.comments_path(uid)
        if not path.exists():
            return []
        data = load_yaml(path)
        return data if isinstance(data, list) else []

    def add_comment(
        self, uid: str, text: str, author: str,
        reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        (self.root / "comments").mkdir(exist_ok=True)
        comments = self.get_comments(uid)
        comment = {
            "uid": uuid7(),
            "text": text,
            "author": author,
            "created_at": utcnow_iso(),
            "updated_at": None,
            "reply_to": reply_to,
            "resolved": False,
        }
        comments.append(comment)
        save_yaml(self.comments_path(uid), comments)
        return comment

    def update_comment(self, uid: str, comment_uid: str, text: str) -> Optional[dict[str, Any]]:
        comments = self.get_comments(uid)
        for c in comments:
            if c.get("uid") == comment_uid:
                c["text"] = text
                c["updated_at"] = utcnow_iso()
                save_yaml(self.comments_path(uid), comments)
                return c
        return None

    def resolve_comment(self, uid: str, comment_uid: str, resolved: bool = True) -> Optional[dict[str, Any]]:
        comments = self.get_comments(uid)
        for c in comments:
            if c.get("uid") == comment_uid:
                c["resolved"] = resolved
                save_yaml(self.comments_path(uid), comments)
                return c
        return None

    def delete_comment(self, uid: str, comment_uid: str) -> bool:
        comments = self.get_comments(uid)
        new = [c for c in comments if c.get("uid") != comment_uid]
        if len(new) == len(comments):
            return False
        save_yaml(self.comments_path(uid), new)
        return True

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

    # ------------------------------------------------------------------
    # Hierarchy helpers
    # ------------------------------------------------------------------

    def get_workflow_for_type(self, req_type: str) -> Optional[HierarchyWorkflowDef]:
        """Return the HierarchyWorkflowDef for a given req_type, or None."""
        type_cfg = self.hierarchy.types.get(req_type)
        if not type_cfg:
            return None
        return self.hierarchy.workflows.get(type_cfg.workflow)

    def get_allowed_children(self, req_type: str) -> list[str]:
        """Return the list of allowed child types for a given parent type."""
        rule = self.hierarchy.hierarchy.get(req_type)
        if rule is None:
            return []
        return rule.allowed_children

    def check_transition_guard(
        self, req: dict[str, Any], to_state: str
    ) -> Optional[str]:
        """
        Check if transitioning to `to_state` satisfies all guards.
        Returns an error message string if blocked, or None if allowed.
        """
        req_type = req.get("req_type", "functional")
        wf = self.get_workflow_for_type(req_type)
        if not wf:
            return None  # No workflow configured -- allow all transitions
        guard = wf.guards.get(to_state)
        if not guard:
            return None  # No guard for this state

        # Check required fields
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

        # Check required AC
        if guard.requires_ac and not req.get("acceptance_criteria"):
            return guard.message or f"At least one acceptance criterion is required before transitioning to '{to_state}'."

        return None

    def validate_transition(
        self, req: dict[str, Any], to_state: str
    ) -> Optional[str]:
        """
        Validate that the transition from the current status to `to_state` is permitted
        by the workflow definition.  Returns an error message or None if allowed.
        """
        req_type = req.get("req_type", "functional")
        current = req.get("status", "draft")
        wf = self.get_workflow_for_type(req_type)
        if not wf:
            # No hierarchy workflow -- fall back to config workflow
            allowed = self.config.workflow.transitions.get(current, [])
            if to_state not in allowed and to_state != current:
                return f"Transition from '{current}' to '{to_state}' is not permitted."
            return None
        allowed = wf.transitions.get(current, [])
        if to_state not in allowed and to_state != current:
            return f"Transition from '{current}' to '{to_state}' is not permitted for type '{req_type}'."
        return self.check_transition_guard(req, to_state)

    def next_id_for_type(self, req_type: str) -> str:
        """
        Auto-increment ID for a given req_type based on the configured prefix.
        Looks at all existing requirement IDs and finds the highest numeric suffix.
        """
        type_cfg = self.hierarchy.types.get(req_type)
        prefix = type_cfg.id_prefix if type_cfg else req_type.upper()[:3]

        max_n = 0
        for req in self.requirements.values():
            rid = req.get("id", "")
            if rid.startswith(prefix + "-"):
                try:
                    n = int(rid[len(prefix) + 1:])
                    if n > max_n:
                        max_n = n
                except ValueError:
                    pass
        return f"{prefix}-{max_n + 1:03d}"

    def default_checklist(self, kind: str, req_type: str) -> list[dict[str, Any]]:
        """Return default DoR or DoD checklist items for a type, with checked=False."""
        templates = self.hierarchy.dor if kind == "dor" else self.hierarchy.dod
        items = templates.get(req_type, [])
        return [{"item": i.get("item", ""), "checked": False} for i in items]

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

    def compute_estimate_rollup(self, uid: str) -> Optional[float]:
        """Sum of direct children's estimate values, or None if no children have estimates."""
        children = [
            r for r in self.requirements.values()
            if not r.get("deleted") and r.get("parentId") == uid
        ]
        if not children:
            return None
        estimates = [r.get("estimate") for r in children if r.get("estimate") is not None]
        if not estimates:
            return None
        return sum(estimates)

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

        module_dir = self.root / "modules" / module_id
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

        lock_path = self.root / "products" / product_id / "_product.lock"
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
        lock_path = self.root / "products" / product_id / "_product.lock"
        if not lock_path.exists():
            return {"verified": False, "reason": "lock file missing"}
        try:
            lock = load_yaml(lock_path)
        except Exception as e:
            return {"verified": False, "reason": f"lock parse error: {e}"}

        locked = next((m for m in lock.get("locked", []) if m.get("id") == module_id), None)
        if not locked:
            return {"verified": False, "reason": f"module '{module_id}' not in lock"}

        module_dir = self.root / "modules" / module_id
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

    def compute_affected_requirements(self, tbd_uid: str) -> list[str]:
        """Return UIDs of requirements that reference this TBD in their relationships."""
        affected = []
        for uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            for rel in req.get("relationships", []):
                if rel.get("uid") == tbd_uid or rel.get("ref") == tbd_uid:
                    affected.append(uid)
                    break
        return affected

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
        return results[:limit]

