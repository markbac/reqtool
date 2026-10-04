"""API request and result bodies."""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

from .entities import *  # noqa: F401,F403
from .config import *  # noqa: F401,F403

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
    target_release: Optional[str] = None
    target_milestone: Optional[str] = None
    release_status: Optional[str] = None
    planned_start_date: Optional[str] = None
    planned_completion_date: Optional[str] = None
    safety_standard: Optional[str] = None
    asil_level: Optional[str] = None
    dal_level: Optional[str] = None
    mitigates_hazard: Optional[str] = None
    source_document: Optional[str] = None
    legal_compliance_status: Optional[str] = None
    compliance_rationale: Optional[str] = None


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
    target_release: Optional[str] = None
    target_milestone: Optional[str] = None
    release_status: Optional[str] = None
    planned_start_date: Optional[str] = None
    planned_completion_date: Optional[str] = None
    safety_standard: Optional[str] = None
    asil_level: Optional[str] = None
    dal_level: Optional[str] = None
    mitigates_hazard: Optional[str] = None
    source_document: Optional[str] = None
    legal_compliance_status: Optional[str] = None
    compliance_rationale: Optional[str] = None


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
    supersedes: Optional[str] = None
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
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    tags: Optional[list[str]] = None
    links: Optional[list[dict[str, Any]]] = None


CreateDecisionRequest = CreateTBDRequest
UpdateDecisionRequest = UpdateTBDRequest


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
    # When given, the approval is bound to this content hash and refused if the content has since changed (FEAT-04).
    content_hash: Optional[str] = None


class ResolveRequest(BaseModel):
    """Resolve a TBD or accept a decision. ``resolution`` is the older name for ``decision``."""
    decision: Optional[str] = None
    resolution: Optional[str] = None
    rationale: Optional[str] = None
    linked_decision: Optional[str] = None
    resolved_by: Optional[str] = None

    def decision_text(self) -> Optional[str]:
        return self.decision or self.resolution


class ValidationResult(BaseModel):
    errors: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[dict[str, str]] = Field(default_factory=list)


class GitStatusResult(BaseModel):
    staged: list[str] = Field(default_factory=list)
    unstaged: list[str] = Field(default_factory=list)
    untracked: list[str] = Field(default_factory=list)
