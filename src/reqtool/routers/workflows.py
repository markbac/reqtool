"""
reqtool.routers.workflows
=========================
Workflow administration: the definitions stored in the repository's hierarchy.yaml, their Mermaid diagrams,
and which workflow each item type uses. Changing anything is for administrators (see ``permissions``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from reqtool import workflows as wf_lib
from reqtool.services.workflows import WorkflowService
from reqtool.store import Store
from .deps import get_store

router = APIRouter(tags=["workflows"])


def get_service(store: Store = Depends(get_store)) -> WorkflowService:
    return WorkflowService(store)


@router.get("/workflows")
def list_workflows(service: WorkflowService = Depends(get_service)):
    """Every workflow with the item types that use it, its problems and its Mermaid diagram."""
    return service.list_all()


@router.post("/workflows/preview")
def preview_workflow(body: dict[str, Any], service: WorkflowService = Depends(get_service)):
    """Check and draw a definition without saving it (for the editor's live preview)."""
    return service.preview(body.get("definition") or {}, body.get("id"))


@router.post("/workflows", status_code=201)
def create_workflow(body: dict[str, Any], service: WorkflowService = Depends(get_service)):
    return service.create(str(body.get("id", "")).strip(), body.get("copy_from"), body.get("definition"))


@router.get("/workflows/{workflow_id}")
def get_workflow_definition(workflow_id: str, service: WorkflowService = Depends(get_service)):
    return service.describe(workflow_id)


@router.get("/workflows/{workflow_id}/mermaid")
def workflow_mermaid(workflow_id: str, service: WorkflowService = Depends(get_service)):
    described = service.describe(workflow_id)
    return {"id": workflow_id, "mermaid": described["mermaid"]}


@router.put("/workflows/{workflow_id}")
def save_workflow(workflow_id: str, body: dict[str, Any], service: WorkflowService = Depends(get_service)):
    return service.save(workflow_id, body)


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str, service: WorkflowService = Depends(get_service)):
    return service.delete(workflow_id)


@router.put("/hierarchy/types/{type_id}/workflow")
def assign_workflow(type_id: str, body: dict[str, Any], service: WorkflowService = Depends(get_service)):
    return service.assign(type_id, str(body.get("workflow", "")))


@router.get("/workflow/mermaid")
def global_workflow_mermaid(store: Store = Depends(get_store)):
    """The repository-wide fallback workflow (config.yaml), used for item types with no workflow of their own."""
    definition = wf_lib.normalise(store.config.workflow.model_dump())
    return {"id": "global", "mermaid": wf_lib.to_mermaid(definition)}
