"""What the validation rules need to know about a repository, without the ``Store`` (ARC-05).

Rules used to take the whole store and index into its dicts, so a rule that needed more context had to reach for
yet another store attribute. They now take a ``ValidationContext``: plain data plus one injected callable. A test
can build one by hand and run every rule with no store, no files and no git.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

from .models import HierarchyConfig, RepoConfig

if TYPE_CHECKING:
    from .store import Store

Artefacts = Mapping[str, dict[str, Any]]


@dataclass
class ValidationContext:
    root: Path
    requirements: Artefacts
    principles: Artefacts = field(default_factory=dict)
    decisions: Artefacts = field(default_factory=dict)
    products: Artefacts = field(default_factory=dict)
    all_uids: set[str] = field(default_factory=set)
    merged_enums: dict[str, Any] = field(default_factory=dict)
    cfg: Any = field(default_factory=lambda: RepoConfig().validation)   # the config.validation policy
    hierarchy: HierarchyConfig = field(default_factory=HierarchyConfig)
    nfr_keys: frozenset[str] = frozenset()
    known_tags: frozenset[str] = frozenset()
    known_teams: frozenset[str] = frozenset()
    known_owners: frozenset[str] = frozenset()
    known_safety: frozenset[str] = frozenset()
    # Custom-field rules live with the schema file; the caller supplies them.
    custom_field_errors: Callable[[dict[str, Any]], list[dict[str, str]]] = lambda req: []

    @property
    def req_status_by_uid(self) -> dict[str, str]:
        return {uid: r.get("status", "") for uid, r in self.requirements.items()}

    @property
    def open_tbd_uids(self) -> set[str]:
        return {uid for uid, t in self.decisions.items()
                if not t.get("deleted") and t.get("status") in ("open", "in_progress")}

    def hierarchy_problem(self, child_type: str, parent_uid: Optional[str]) -> Optional[str]:
        """Message if ``child_type`` is not allowed under ``parent_uid``'s type (ignores the enforce mode)."""
        from .stores import hierarchy_store
        parent = self.requirements.get(parent_uid) if parent_uid else None
        if not parent:
            return None
        return hierarchy_store.check_parent_type(self.hierarchy, parent.get("req_type", "functional"), child_type)

    def relationship_problem(self, source_type: str, rel: dict[str, Any]) -> Optional[str]:
        """Message if ``rel`` breaks the cross-layer rules for a source of ``source_type``."""
        from .stores import hierarchy_store
        target = self.requirements.get((rel.get("target") or {}).get("uid", ""))
        if not target or not rel.get("type"):
            return None
        return hierarchy_store.check_relationship(
            self.hierarchy, source_type, target.get("req_type", "functional"), rel["type"])

    @classmethod
    def from_store(cls, store: "Store") -> "ValidationContext":
        enums = store.repo_enums
        return cls(
            root=store.root,
            requirements=store.requirement_map(),
            principles=store.principle_map(),
            decisions=store.decision_map(),
            products=store.product_map(),
            all_uids=store.all_uids(),
            merged_enums=store.merged_enums(),
            cfg=store.config.validation,
            hierarchy=store.hierarchy,
            nfr_keys=frozenset(enums.nfr_keys),
            known_tags=frozenset(enums.tags or ()),
            known_teams=frozenset(enums.team or ()),
            known_owners=frozenset(enums.owner or ()),
            known_safety=frozenset(enums.safety_class or ()),
            custom_field_errors=store.validate_custom_fields,
        )
