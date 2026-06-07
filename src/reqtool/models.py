"""
reqtool.models
==============
Pydantic v2 models for all reqtool artefact types.
Mirrors the YAML schema defined in the specification (v1.0.0).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class Link(BaseModel):
    system: str
    type: str
    ref: str
    title: str = ""
    ref_type: Optional[str] = None
    system_name: Optional[str] = None  # only when system == "other"


class Relationship(BaseModel):
    type: str
    target: dict[str, str]  # {"uid": "<uuid>"}


class HistoryEntry(BaseModel):
    version: str
    date: datetime
    modified_by: str
    summary: str
    commit_sha: Optional[str] = None
    change_ref: Optional[str] = None


class ChangelogEntry(BaseModel):
    version: str
    date: datetime
    author: str
    summary: str
    commit_sha: Optional[str] = None
    change_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Acceptance Criterion
# ---------------------------------------------------------------------------

class AcceptanceCriterion(BaseModel):
    uid: str
    id: str
    text: str
    links: list[Link] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DoR / DoD checklist item
# ---------------------------------------------------------------------------

class ChecklistItem(BaseModel):
    item: str
    checked: bool = False


# ---------------------------------------------------------------------------
# Requirement sub-objects
# ---------------------------------------------------------------------------

class RequirementContent(BaseModel):
    description: str = ""
    rationale: str = ""
    extended_description: str = ""


class VerificationBlock(BaseModel):
    status: str = "not_started"
    verified_date: Optional[datetime] = None
    note: str = ""


class ApprovalBlock(BaseModel):
    status: str = "draft"
    approved_by: Optional[str] = None
    approved_date: Optional[datetime] = None


class ReviewBlock(BaseModel):
    last_reviewed: Optional[datetime] = None
    reviewers: list[str] = Field(default_factory=list)
    note: str = ""


class ImplementationBlock(BaseModel):
    status: str = "not_started"
    branch: Optional[str] = None


# ---------------------------------------------------------------------------
# Requirement
# ---------------------------------------------------------------------------

class Requirement(BaseModel):
    schema_version: str = "1.0.0"
    type: Literal["requirement"] = "requirement"
    tool_version: str = "0.1.0"

    uid: str
    id: str
    parent_id: Optional[str] = Field(None, alias="parentId")
    title: str
    version: str = "1.0.0"

    content: RequirementContent = Field(default_factory=RequirementContent)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)

    status: str = "draft"
    priority: str = "medium"
    req_type: str = "functional"
    domain: Optional[str] = None
    feature: Optional[str] = None

    owner: Optional[str] = None
    assignee: Optional[str] = None
    component: Optional[str] = None
    allocated_to: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    iteration: Optional[str] = None
    estimate: Optional[float] = None
    estimate_unit: Optional[str] = None

    attributes: dict[str, Any] = Field(default_factory=dict)
    nfr: dict[str, float] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    relationships: list[Relationship] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)

    risk: str = "none"
    safety_related: bool = False
    safety_classification: Optional[str] = None

    verification_method: str = "test"
    verification: VerificationBlock = Field(default_factory=VerificationBlock)
    approval: ApprovalBlock = Field(default_factory=ApprovalBlock)
    review: ReviewBlock = Field(default_factory=ReviewBlock)
    implementation: ImplementationBlock = Field(default_factory=ImplementationBlock)

    dor_checklist: list[ChecklistItem] = Field(default_factory=list)
    dod_checklist: list[ChecklistItem] = Field(default_factory=list)

    content_hash: str = ""
    created: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    deleted: bool = False
    history: list[HistoryEntry] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Principle
# ---------------------------------------------------------------------------

class PrincipleContent(BaseModel):
    description: str = ""
    rationale: str = ""
    implications: str = ""
    exceptions: str = ""


class Principle(BaseModel):
    schema_version: str = "1.0.0"
    type: Literal["principle"] = "principle"
    tool_version: str = "0.1.0"

    uid: str
    id: str
    title: str
    version: str = "1.0.0"

    content: PrincipleContent = Field(default_factory=PrincipleContent)

    domain: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    owner: Optional[str] = None
    links: list[Link] = Field(default_factory=list)

    status: str = "draft"
    approval: ApprovalBlock = Field(default_factory=ApprovalBlock)
    review: ReviewBlock = Field(default_factory=ReviewBlock)

    content_hash: str = ""
    created: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    deleted: bool = False
    history: list[HistoryEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TBD
# ---------------------------------------------------------------------------

class TBDContent(BaseModel):
    description: str = ""
    impact: str = ""
    resolution_criteria: str = ""
    resolution: Optional[str] = None


class TBD(BaseModel):
    schema_version: str = "1.0.0"
    type: Literal["tbd"] = "tbd"
    tool_version: str = "0.1.0"

    uid: str
    id: str
    title: str
    version: str = "1.0.0"

    content: TBDContent = Field(default_factory=TBDContent)

    owner: Optional[str] = None
    due: Optional[str] = None
    status: str = "open"
    priority: str = "medium"
    affected_requirements: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    content_hash: str = ""
    created: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    deleted: bool = False
    history: list[HistoryEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Module Manifest
# ---------------------------------------------------------------------------

class ModuleContent(BaseModel):
    description: str = ""
    scope: str = ""


class ModuleRequirementRef(BaseModel):
    uid: str
    id: str


class Module(BaseModel):
    schema_version: str = "1.0.0"
    type: Literal["module"] = "module"
    tool_version: str = "0.1.0"

    uid: str
    id: str
    title: str
    version: str = "1.0.0"

    content: ModuleContent = Field(default_factory=ModuleContent)
    owner: Optional[str] = None
    domain: Optional[str] = None
    tags: list[str] = Field(default_factory=list)

    requirements: list[ModuleRequirementRef] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    overrideable: list[str] = Field(default_factory=list)
    compatible_domains: list[str] = Field(default_factory=list)
    applicable_standards: list[str] = Field(default_factory=list)

    source: str = ""
    path: str = ""

    content_hash: str = ""
    created: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    deleted: bool = False
    changelog: list[ChangelogEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Product Manifest
# ---------------------------------------------------------------------------

class ProductContent(BaseModel):
    description: str = ""


class ProductVariant(BaseModel):
    id: str
    title: str
    description: str = ""


class ModuleOverrideRef(BaseModel):
    id: str
    version: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class Product(BaseModel):
    schema_version: str = "1.0.0"
    type: Literal["product"] = "product"
    tool_version: str = "0.1.0"

    uid: str
    id: str
    title: str
    version: str = "1.0.0"

    content: ProductContent = Field(default_factory=ProductContent)
    owner: Optional[str] = None

    variants: list[ProductVariant] = Field(default_factory=list)
    modules: list[ModuleOverrideRef] = Field(default_factory=list)
    root_requirements: list[dict[str, str]] = Field(default_factory=list)
    display_order: list[dict[str, str]] = Field(default_factory=list)

    content_hash: str = ""
    created: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    history: list[HistoryEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Lock file
# ---------------------------------------------------------------------------

class LockedModule(BaseModel):
    id: str
    version: str
    ref: str
    sha: str
    content_hash: str
    locked_at: datetime
    locked_by: str


class ProductLock(BaseModel):
    schema_version: str = "1.0.0"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generated_by: str = "reqtool"
    locked: list[LockedModule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Enums config
# ---------------------------------------------------------------------------

class CoreEnums(BaseModel):
    status: list[str] = ["draft", "in_review", "approved", "deprecated"]
    priority: list[str] = ["critical", "high", "medium", "low"]
    req_type: list[str] = [
        "functional", "performance", "interface", "physical",
        "safety", "security", "compliance", "operational", "constraint",
    ]
    approval_status: list[str] = ["draft", "in_review", "approved", "rejected", "deprecated"]
    verification_method: list[str] = ["analysis", "inspection", "test", "demonstration"]
    verification_status: list[str] = [
        "not_started", "planned", "in_progress", "passed", "failed", "waived",
    ]
    implementation_status: list[str] = [
        "not_started", "in_progress", "implemented", "verified", "deferred", "cancelled",
    ]
    tbd_status: list[str] = ["open", "in_progress", "resolved", "cancelled"]
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
    id_domain: dict[str, str] = Field(default_factory=dict)
    estimate_unit: str = "points"                              # repo-wide estimate unit label
    relationship_types: list[str] = Field(default_factory=list)  # extends core relationship_type


# ---------------------------------------------------------------------------
# Repo config
# ---------------------------------------------------------------------------

class WebhookConfig(BaseModel):
    url: str
    events: list[str] = Field(default_factory=lambda: ["status_changed", "approved", "comment_added"])
    secret: Optional[str] = None
    enabled: bool = True


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
        "draft":      ["in_review", "approved"],
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


class ExportConfig(BaseModel):
    output_dir: str = "exports/"
    jsx: ExportJsxConfig = Field(default_factory=ExportJsxConfig)
    markdown: ExportMarkdownConfig = Field(default_factory=ExportMarkdownConfig)
    csv: ExportCsvConfig = Field(default_factory=ExportCsvConfig)


class ValidationConfig(BaseModel):
    require_rationale_for_approved: bool = True
    require_ac_for_approved: bool = True
    require_owner: bool = True
    warn_on_missing_test_ref: bool = True
    warn_on_open_tbds_in_approved: bool = True
    max_history_entries: int = 20


class RepoConfig(BaseModel):
    schema_version: str = "1.0.0"
    repo_id: str = ""
    repo_title: str = ""
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
    message: str = ""


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


class HierarchyConfig(BaseModel):
    types: dict[str, ItemTypeConfig] = Field(default_factory=dict)
    hierarchy: dict[str, HierarchyRule] = Field(default_factory=dict)
    workflows: dict[str, HierarchyWorkflowDef] = Field(default_factory=dict)
    dor: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    dod: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    cross_layer_rules: list[CrossLayerRule] = Field(default_factory=list)
    default_relationship_types: list[RelationshipTypeDef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Filter preset (saved in .reqtool/filter_presets.yaml)
# ---------------------------------------------------------------------------

class FilterPreset(BaseModel):
    id: str
    label: str
    filters: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# API request/response shapes
# ---------------------------------------------------------------------------

class BulkUpdateRequest(BaseModel):
    uids: list[str]
    fields: dict[str, Any]  # e.g. {"status": "approved", "owner": "mb"}
    summary: str = "Bulk update"
    increment: Literal["patch", "minor", "major"] = "patch"


class CreateRequirementRequest(BaseModel):
    """Body for POST /requirements. All fields are optional except title."""
    id: Optional[str] = None
    parentId: Optional[str] = None
    title: str
    req_type: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    acceptance_criteria: Optional[list[dict[str, Any]]] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    domain: Optional[str] = None
    discipline: Optional[str] = None
    feature: Optional[str] = None
    owner: Optional[str] = None
    assignee: Optional[str] = None
    component: Optional[str] = None
    allocated_to: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    iteration: Optional[str] = None
    estimate: Optional[float] = None
    estimate_unit: Optional[str] = None
    dor_checklist: Optional[list[dict[str, Any]]] = None
    dod_checklist: Optional[list[dict[str, Any]]] = None
    attributes: Optional[dict[str, Any]] = None
    custom_fields: Optional[dict[str, Any]] = None
    nfr: Optional[dict[str, Any]] = None
    constraints: Optional[list[str]] = None
    assumptions: Optional[list[str]] = None
    relationships: Optional[list[dict[str, Any]]] = None
    links: Optional[list[dict[str, Any]]] = None
    attachments: Optional[list[dict[str, Any]]] = None
    risk: Optional[str] = None
    safety_related: Optional[bool] = None
    safety_classification: Optional[str] = None
    verification_method: Optional[str] = None
    verification: Optional[dict[str, Any]] = None
    approval: Optional[dict[str, Any]] = None
    review: Optional[dict[str, Any]] = None
    implementation: Optional[dict[str, Any]] = None


class UpdateRequirementRequest(BaseModel):
    """Body for PUT /requirements/{uid}. All fields are optional."""
    id: Optional[str] = None
    parentId: Optional[str] = None
    title: Optional[str] = None
    req_type: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    acceptance_criteria: Optional[list[dict[str, Any]]] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    domain: Optional[str] = None
    discipline: Optional[str] = None
    feature: Optional[str] = None
    owner: Optional[str] = None
    assignee: Optional[str] = None
    component: Optional[str] = None
    allocated_to: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    iteration: Optional[str] = None
    estimate: Optional[float] = None
    estimate_unit: Optional[str] = None
    dor_checklist: Optional[list[dict[str, Any]]] = None
    dod_checklist: Optional[list[dict[str, Any]]] = None
    attributes: Optional[dict[str, Any]] = None
    custom_fields: Optional[dict[str, Any]] = None
    nfr: Optional[dict[str, Any]] = None
    constraints: Optional[list[str]] = None
    assumptions: Optional[list[str]] = None
    relationships: Optional[list[dict[str, Any]]] = None
    links: Optional[list[dict[str, Any]]] = None
    attachments: Optional[list[dict[str, Any]]] = None
    risk: Optional[str] = None
    safety_related: Optional[bool] = None
    safety_classification: Optional[str] = None
    verification_method: Optional[str] = None
    verification: Optional[dict[str, Any]] = None
    approval: Optional[dict[str, Any]] = None
    review: Optional[dict[str, Any]] = None
    implementation: Optional[dict[str, Any]] = None


class CreatePrincipleRequest(BaseModel):
    id: Optional[str] = None
    title: str
    content: Optional[dict[str, Any]] = None
    domain: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[list[str]] = None
    links: Optional[list[dict[str, Any]]] = None
    approval: Optional[dict[str, Any]] = None


class UpdatePrincipleRequest(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    domain: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[list[str]] = None
    links: Optional[list[dict[str, Any]]] = None
    approval: Optional[dict[str, Any]] = None


class CreateTBDRequest(BaseModel):
    id: Optional[str] = None
    title: str
    content: Optional[dict[str, Any]] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    owner: Optional[str] = None
    due: Optional[str] = None
    tags: Optional[list[str]] = None
    links: Optional[list[dict[str, Any]]] = None


class UpdateTBDRequest(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    owner: Optional[str] = None
    due: Optional[str] = None
    tags: Optional[list[str]] = None
    links: Optional[list[dict[str, Any]]] = None


class AddACRequest(BaseModel):
    id: Optional[str] = None
    text: str
    links: Optional[list[dict[str, Any]]] = None


class UpdateACRequest(BaseModel):
    id: Optional[str] = None
    text: Optional[str] = None
    links: Optional[list[dict[str, Any]]] = None


class ExportRequest(BaseModel):
    product: Optional[str] = None
    variant: Optional[str] = None


class ExportMarkdownRequest(ExportRequest):
    split_by: Optional[Literal["domain", "product", "none"]] = None


class ExportCSVRequest(ExportRequest):
    fields: Optional[list[str]] = None


class CommitRequest(BaseModel):
    message: str
    increment: Literal["patch", "minor", "major"] = "patch"
    change_ref: Optional[str] = None
    uids: list[str] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    approved_by: str


class ResolveRequest(BaseModel):
    resolution: str
    resolved_by: str


class ValidationResult(BaseModel):
    errors: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[dict[str, str]] = Field(default_factory=list)


class GitStatusResult(BaseModel):
    staged: list[str] = Field(default_factory=list)
    unstaged: list[str] = Field(default_factory=list)
    untracked: list[str] = Field(default_factory=list)
