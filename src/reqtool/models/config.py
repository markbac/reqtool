"""Repository, workflow, hierarchy and export configuration."""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums config
# ---------------------------------------------------------------------------

class CoreEnums(BaseModel):
    status: list[str] = [
        # Formal / systems workflow
        "draft", "in_review", "reviewed", "approved", "deprecated",
        # Sprint / agile workflow
        "backlog", "ready", "in_progress", "done", "cancelled",
        # Lightweight workflow
        "active",
        # TBD
        "open", "resolved",
    ]
    priority: list[str] = ["critical", "high", "medium", "low"]
    req_type: list[str] = [
        # Systems engineering types
        "functional", "performance", "interface", "physical",
        "safety", "security", "compliance", "operational", "constraint",
        # Stakeholder / top-level
        "stakeholder_need",
        # Agile planning types
        "theme", "initiative", "epic", "feature",
        "story", "task", "bug", "spike",
    ]
    approval_status: list[str] = ["draft", "in_review", "approved", "rejected", "deprecated"]
    verification_method: list[str] = ["analysis", "inspection", "test", "demonstration"]
    verification_status: list[str] = [
        "not_started", "planned", "in_progress", "passed", "failed", "waived",
    ]
    implementation_status: list[str] = [
        "not_started", "in_progress", "implemented", "verified", "deferred", "cancelled",
    ]
    tbd_status: list[str] = [
        "proposed", "accepted", "rejected", "superseded",
        "open", "in_progress", "resolved", "cancelled",
    ]
    risk_level: list[str] = ["critical", "high", "medium", "low", "none"]
    relationship_type: list[str] = [
        "relates_to", "depends_on", "depended_by", "satisfies", "implements",
        "traces_to", "derived_from", "conflicts_with", "supersedes",
    ]
    link_system: list[str] = [
        "standards", "regulation", "jira", "azure_devops", "github",
        "adr", "test_management", "sharepoint", "confluence", "other",
    ]
    link_type: list[str] = [
        "implements", "compliance", "backlog_item", "source_document",
        "governed_by", "test_case", "test_suite", "references", "issue", "tbd",
    ]


class RepoEnums(BaseModel):
    domain: list[str] = Field(default_factory=list)
    discipline: list[str] = Field(default_factory=list)
    feature: list[str] = Field(default_factory=list)
    component: list[str] = Field(default_factory=list)
    team: list[str] = Field(default_factory=list)
    owner: list[str] = Field(default_factory=list)
    safety_class: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    nfr_keys: list[str] = Field(default_factory=list)
    verification_method: list[str] = Field(default_factory=list)
    priority: list[str] = Field(default_factory=list)
    risk: list[str] = Field(default_factory=list)
    id_domain: dict[str, str] = Field(default_factory=dict)
    estimate_unit: str = "points"                              # repo-wide estimate unit label
    relationship_types: list[str] = Field(default_factory=list)  # extends core relationship_type
    # Principle vocabulary: area -> {label, code, categories: {category: {label, code}}}. Empty means the defaults.
    principle_areas: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Repo config
# ---------------------------------------------------------------------------

class WebhookConfig(BaseModel):
    url: str
    events: list[str] = Field(default_factory=lambda: ["status_changed", "approved", "comment_added"])
    secret: Optional[str] = None
    enabled: bool = True
    # Allow targets on loopback/private/link-local networks (off by default: SSRF guard)
    allow_private: bool = False
    # json (default), or slack / teams for a one-line text message (FEAT-10)
    format: Literal["json", "slack", "teams"] = "json"


class CustomFieldDef(BaseModel):
    key: str
    label: str
    type: Literal["string", "number", "boolean", "select", "multiselect", "date"] = "string"
    options: list[str] = Field(default_factory=list)   # for select / multiselect
    required: bool = False
    description: str = ""
    default: Optional[Any] = None
    applies_to: list[str] = Field(default_factory=lambda: ["requirement"])  # requirement / principle / tbd


class WorkflowState(BaseModel):
    id: str
    label: str
    colour: str = "#8b949e"
    description: str = ""
    terminal: bool = False


class WorkflowConfig(BaseModel):
    initial: str = "draft"
    states: list[WorkflowState] = Field(default_factory=lambda: [
        WorkflowState(id="draft",      label="Draft",      colour="#8b949e"),
        WorkflowState(id="in_review",  label="In Review",  colour="#d29922"),
        WorkflowState(id="reviewed",   label="Reviewed",   colour="#1f6feb"),
        WorkflowState(id="approved",   label="Approved",   colour="#238636"),
        WorkflowState(id="deprecated", label="Deprecated", colour="#da3633", terminal=True),
    ])
    transitions: dict[str, list[str]] = Field(default_factory=lambda: {
        "draft":      ["in_review"],
        "in_review":  ["reviewed", "draft"],
        "reviewed":   ["approved", "in_review"],
        "approved":   ["deprecated", "in_review"],
        "deprecated": [],
    })

    @property
    def state_ids(self) -> list[str]:
        return [s.id for s in self.states]

    @property
    def terminal_states(self) -> list[str]:
        return [s.id for s in self.states if s.terminal]


class GitConfig(BaseModel):
    default_branch: str = "main"
    commit_name: str = "Requirements Tool"
    commit_email: str = "reqtool@example.com"
    sign_commits: bool = False
    post_commit_hook: bool = True


class UIConfig(BaseModel):
    default_product: Optional[str] = None
    theme: str = "light"


class ExportJsxConfig(BaseModel):
    component_name: str = "RequirementsViewer"
    include_principles: bool = True
    include_tbds: bool = True


class ExportMarkdownConfig(BaseModel):
    flavor: str = "mkdocs"
    split_by: str = "domain"


class ExportCsvConfig(BaseModel):
    delimiter: str = ","
    include_fields: list[str] = Field(default_factory=list)


class ExportPdfConfig(BaseModel):
    header_text: str = "reqtool Requirements Specification & Architecture Dossier"  # running header
    footer_text: str = "CONFIDENTIAL & PROPRIETARY \u2014 FOR INTERNAL USE ONLY"       # running footer (classification)
    fallback_font: str = ""  # path to a TrueType font (.ttf/.ttc) used for CJK text; empty = look for one on the system


class ExportConfig(BaseModel):
    output_dir: str = "exports/"
    pdf: ExportPdfConfig = Field(default_factory=ExportPdfConfig)
    jsx: ExportJsxConfig = Field(default_factory=ExportJsxConfig)
    markdown: ExportMarkdownConfig = Field(default_factory=ExportMarkdownConfig)
    csv: ExportCsvConfig = Field(default_factory=ExportCsvConfig)


class ValidationConfig(BaseModel):
    require_rationale_for_approved: bool = True
    require_ac_for_approved: bool = True
    require_owner: bool = True
    warn_on_missing_test_ref: bool = True
    warn_on_open_tbds_in_approved: bool = True
    block_approval_on_open_tbds: bool = False  # policy: refuse approval while a linked TBD is open
    max_history_entries: int = 20


class RepoConfig(BaseModel):
    schema_version: str = "1.0.0"
    repo_id: str = ""
    repo_title: str = ""
    repo_description: str = ""
    git: GitConfig = Field(default_factory=GitConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    webhooks: list[WebhookConfig] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Hierarchy configuration (loaded from hierarchy.yaml)
# ---------------------------------------------------------------------------

class ItemTypeConfig(BaseModel):
    label: str
    icon: str = ""
    color: str = "#8b949e"
    description: str = ""
    workflow: str = "formal"
    id_prefix: str = "REQ"


class HierarchyRule(BaseModel):
    allowed_children: list[str] = Field(default_factory=list)


class CrossLayerRule(BaseModel):
    source_types: list[str]
    target_types: list[str]
    allowed_rel_types: list[str]
    note: str = ""


class RelationshipTypeDef(BaseModel):
    id: str
    label: str
    directional: bool = True
    computed: bool = False
    description: str = ""


class WorkflowGuard(BaseModel):
    requires_fields: list[str] = Field(default_factory=list)
    requires_ac: bool = False
    # Direct children must all be in one of these states before the item may enter the guarded state.
    requires_children_in: list[str] = Field(default_factory=list)
    # off | warn | error. warn only reports `open_children` in validation; error also blocks the transition.
    children_enforce: str = "warn"
    message: str = ""

    @field_validator("children_enforce", mode="before")
    @classmethod
    def _valid_children_enforce(cls, v):
        v = str(v or "warn").strip().lower()
        return v if v in ("off", "warn", "error") else "warn"


class HierarchyWorkflowState(BaseModel):
    id: str
    label: str
    colour: str = "#8b949e"
    terminal: bool = False


class HierarchyWorkflowDef(BaseModel):
    initial: str = "draft"
    states: list[HierarchyWorkflowState] = Field(default_factory=list)
    transitions: dict[str, list[str]] = Field(default_factory=dict)
    guards: dict[str, WorkflowGuard] = Field(default_factory=dict)


RULE_KINDS = ("up", "down", "start", "complete", "reopen", "cancel")
OVERRIDE_LEVELS = ("none", "editor", "admin")


class ParentChildRule(BaseModel):
    """One parent/child rule. See docs/USER_GUIDE.md ("Parent and child rules") for what each kind does.

    ``up`` and ``down`` are checks (mode off/warn/error). ``start``, ``complete``, ``reopen`` and ``cancel`` change
    another item's status (mode off/suggest/auto). State lists may hold state ids or the tokens ``@initial``,
    ``@started``, ``@terminal``, ``@done`` and ``@cancelled``.
    """
    id: str
    kind: str
    label: str = ""
    parent_types: list[str] = Field(default_factory=lambda: ["*"])
    child_types: list[str] = Field(default_factory=lambda: ["*"])
    # up: parent | ancestors.  down, complete, cancel: children | descendants.  start, reopen: parent | ancestors.
    scope: str = "parent"
    levels: Optional[int] = None
    mode: str = "off"
    when_in: list[str] = Field(default_factory=list)
    to: list[str] = Field(default_factory=list)
    children_in: list[str] = Field(default_factory=list)
    override: Optional[str] = None
    reapply: bool = False


class RulesConfig(BaseModel):
    override: str = "editor"
    rules: list[ParentChildRule] = Field(default_factory=list)


class FlowConfig(BaseModel):
    """When an item counts as stuck in the flow view: days in a state, with optional per-state limits."""
    stuck_days: int = Field(14, ge=1, le=3650)
    states: dict[str, int] = Field(default_factory=dict)


class HierarchyConfig(BaseModel):
    types: dict[str, ItemTypeConfig] = Field(default_factory=dict)
    hierarchy: dict[str, HierarchyRule] = Field(default_factory=dict)
    workflows: dict[str, HierarchyWorkflowDef] = Field(default_factory=dict)
    dor: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    dod: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    type_fields: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    cross_layer_rules: list[CrossLayerRule] = Field(default_factory=list)
    default_relationship_types: list[RelationshipTypeDef] = Field(default_factory=list)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    flow: FlowConfig = Field(default_factory=FlowConfig)
    # How hierarchy rules (allowed_children) are applied: off | warn | error
    enforce: str = "warn"


# ---------------------------------------------------------------------------
# Filter preset (saved in .reqtool/filter_presets.yaml)
# ---------------------------------------------------------------------------

class FilterPreset(BaseModel):
    id: str
    label: str
    filters: dict[str, Any] = Field(default_factory=dict)
