"""Domain entities: requirements, principles, decisions, modules and products."""

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
    advisory: bool = False  # shown, but does not block completion


# ---------------------------------------------------------------------------
# Requirement sub-objects
# ---------------------------------------------------------------------------

class RequirementContent(BaseModel):
    description: str = ""
    rationale: str = ""
    extended_description: str = ""
    strategic_goal: str = ""
    target_outcome: str = ""
    business_case: str = ""
    timeframe_years: Optional[str] = None
    executive_sponsor: str = ""
    budget_estimate: Optional[float] = None
    user_role: str = ""
    user_action: str = ""
    user_benefit: str = ""


# Dates in artefact files are ISO strings, kept as written (the files are the record, not these models).
class VerificationBlock(BaseModel):
    status: str = "not_started"
    verified_date: Optional[str] = None
    note: str = ""


class ApprovalBlock(BaseModel):
    status: str = "draft"
    approved_by: Optional[str] = None
    approved_date: Optional[str] = None


class ReviewBlock(BaseModel):
    last_reviewed: Optional[str] = None
    reviewers: list[str] = Field(default_factory=list)
    note: str = ""


class ImplementationBlock(BaseModel):
    status: str = "not_started"
    branch: Optional[str] = None


class Iteration(BaseModel):
    id: str
    title: str
    methodology: Literal["scrum", "waterfall", "wagile", "kanban"] = "scrum"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    milestone_date: Optional[str] = None
    capacity_story_points: float = 0.0
    status: Literal["planned", "active", "completed", "closed"] = "planned"
    product_id: Optional[str] = None
    gate_review_passed: Optional[bool] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Requirement
# ---------------------------------------------------------------------------

def _new_content() -> RequirementContent:
    # A new item stores only the three text fields every type has; the strategic ones are added when used.
    return RequirementContent(description="", rationale="", extended_description="")


def _set(model: type[BaseModel], **values: Any) -> Any:
    """An instance whose fields all count as set, so that dumping with ``exclude_unset`` keeps every key."""
    return model(**values)


class Requirement(BaseModel):
    """A requirement as stored in ``requirements/<uid>.yaml``.

    The field order is the key order of a new file, and ``reqtool.artefacts.new_requirement`` builds new items
    from these defaults. ``tests/unit/test_artefact_models.py`` checks that every stored item still validates.
    """

    schema_version: str = "1.0.0"
    type: Literal["requirement"] = "requirement"
    tool_version: str = "0.3.20"

    uid: str
    id: str
    parent_id: Optional[str] = Field(None, alias="parentId")
    title: str = ""
    version: str = "1.0.0"

    content: RequirementContent = Field(default_factory=_new_content)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)

    status: str = "draft"
    priority: str = "medium"
    req_type: str = "functional"
    domain: Optional[str] = None
    feature: Optional[str] = None
    discipline: Optional[str] = None

    owner: Optional[str] = None
    assignee: Optional[str] = None
    component: Optional[str] = None
    allocated_to: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    iteration: Optional[str] = None
    estimate: Optional[float] = None
    estimate_unit: Optional[str] = None

    dor_checklist: list[ChecklistItem] = Field(default_factory=list)
    dod_checklist: list[ChecklistItem] = Field(default_factory=list)

    attributes: dict[str, Any] = Field(default_factory=dict)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    nfr: dict[str, float] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    relationships: list[Relationship] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)

    risk: str = "none"
    safety_related: bool = False
    safety_classification: Optional[str] = None
    safety_standard: Optional[str] = None
    asil_level: Optional[str] = None
    dal_level: Optional[str] = None
    mitigates_hazard: Optional[str] = None

    source_document: Optional[str] = None
    legal_compliance_status: Optional[str] = None
    compliance_rationale: Optional[str] = None

    target_release: Optional[str] = None
    target_milestone: Optional[str] = None
    release_status: Optional[str] = "unassigned"
    planned_start_date: Optional[str] = None
    planned_completion_date: Optional[str] = None

    verification_method: str = "test"
    verification: VerificationBlock = Field(
        default_factory=lambda: _set(VerificationBlock, status="not_started", verified_date=None, note=""))
    approval: ApprovalBlock = Field(
        default_factory=lambda: _set(ApprovalBlock, status="draft", approved_by=None, approved_date=None))
    review: ReviewBlock = Field(
        default_factory=lambda: _set(ReviewBlock, last_reviewed=None, reviewers=[], note=""))
    implementation: ImplementationBlock = Field(
        default_factory=lambda: _set(ImplementationBlock, status="not_started", branch=None))

    content_hash: str = ""
    created: str = ""
    last_modified: str = ""
    deleted: bool = False
    history: list[dict[str, Any]] = Field(default_factory=list)

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
    tool_version: str = "0.3.20"
    principle_kind: Literal["process_authoring", "product_nfr"] = "process_authoring"

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
# ---------------------------------------------------------------------------
# Decision Record (ADR), ATAM Analysis & TBD
# ---------------------------------------------------------------------------

class ATAMSensitivityPoint(BaseModel):
    attribute: str
    description: str


class ATAMTradeoffPoint(BaseModel):
    attributes: list[str] = Field(default_factory=list)
    description: str


class ATAMAnalysis(BaseModel):
    enabled: bool = True
    quality_attributes: list[str] = Field(default_factory=list)
    sensitivity_points: list[ATAMSensitivityPoint] = Field(default_factory=list)
    tradeoff_points: list[ATAMTradeoffPoint] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    non_risks: list[str] = Field(default_factory=list)


class DecisionOption(BaseModel):
    name: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    risk_level: Optional[str] = None


class DecisionContent(BaseModel):
    context: str = ""
    description: str = ""
    impact: str = ""
    resolution_criteria: str = ""
    resolution: Optional[str] = None
    options: list[DecisionOption] = Field(default_factory=list)
    chosen_option: Optional[str] = None
    rationale: str = ""
    atam: Optional[ATAMAnalysis] = None


class Decision(BaseModel):
    schema_version: str = "1.0.0"
    type: Literal["decision", "tbd"] = "decision"
    tool_version: str = "0.1.0"

    uid: str
    id: str
    title: str
    version: str = "1.0.0"

    content: DecisionContent = Field(default_factory=DecisionContent)

    owner: Optional[str] = None
    due: Optional[str] = None
    status: str = "proposed"  # proposed | accepted | rejected | superseded | open | in_progress | resolved
    priority: str = "medium"
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    affected_requirements: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    content_hash: str = ""
    created: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    deleted: bool = False
    history: list[HistoryEntry] = Field(default_factory=list)




class TBDContent(BaseModel):
    context: str = ""
    description: str = ""
    impact: str = ""
    resolution_criteria: str = ""
    resolution: Optional[str] = None
    options: list[DecisionOption] = Field(default_factory=list)
    chosen_option: Optional[str] = None
    rationale: str = ""
    atam: Optional[ATAMAnalysis] = None


class TBD(BaseModel):
    schema_version: str = "1.0.0"
    type: Literal["tbd", "decision"] = "tbd"
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
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
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
