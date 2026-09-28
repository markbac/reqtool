"""
reqtool.routers.system
======================
FastAPI router for system, config, metadata, hierarchy, kanban, metrics, workflow, help, and template endpoints.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional
from collections import Counter
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response

from reqtool import __version__
from reqtool.store import Store
from reqtool.validation import validate_all
from reqtool.fileio import load_yaml, save_yaml
from reqtool.models import RepoEnums, WorkflowConfig
from .deps import get_store

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", tags=["meta"])
def health(store: Store = Depends(get_store)):
    return {"status": "ok", "version": __version__, "requirements": len(store.requirements)}


@router.get("/version", tags=["meta"])
def get_version(store: Store = Depends(get_store)):
    return {
        "tool_version": __version__,
        "schema_version": "1.0.0",
        "repo_id": store.config.repo_id,
        "repo_title": store.config.repo_title,
    }


@router.get("/search", tags=["meta"])
def search_uids(q: str = "", limit: int = 20, store: Store = Depends(get_store)):
    if not q:
        return []
    return store.search_uids(q, limit)


@router.get("/config", tags=["meta"])
def get_config(store: Store = Depends(get_store)):
    return store.config.model_dump()


@router.get("/enums", tags=["enums"])
def get_enums(store: Store = Depends(get_store)):
    return store.merged_enums()


@router.get("/enums/core", tags=["enums"])
def get_core_enums(store: Store = Depends(get_store)):
    return store.core_enums.model_dump()


@router.get("/enums/repo", tags=["enums"])
def get_repo_enums(store: Store = Depends(get_store)):
    return store.repo_enums.model_dump()


@router.put("/enums/repo", tags=["enums"])
def update_repo_enums(body: dict[str, Any], store: Store = Depends(get_store)):
    enums_path = store.root / ".reqtool" / "enums.yaml"
    save_yaml(enums_path, body)
    store.repo_enums = RepoEnums.model_validate(body)
    return store.repo_enums.model_dump()


@router.get("/custom-fields", tags=["custom-fields"])
def get_custom_field_schema(store: Store = Depends(get_store)):
    return store.load_custom_field_schema()


@router.put("/custom-fields", tags=["custom-fields"])
def save_custom_field_schema(body: list[dict[str, Any]], store: Store = Depends(get_store)):
    store.save_custom_field_schema(body)
    return store.load_custom_field_schema()


@router.get("/webhooks", tags=["webhooks"])
def list_webhooks(store: Store = Depends(get_store)):
    return [w.model_dump() for w in store.config.webhooks]


@router.post("/webhooks", status_code=201, tags=["webhooks"])
def add_webhook(body: dict[str, Any], store: Store = Depends(get_store)):
    from reqtool.models import WebhookConfig
    hook = WebhookConfig.model_validate(body)
    config_path = store.root / ".reqtool" / "config.yaml"
    cfg = load_yaml(config_path) if config_path.exists() else {}
    hooks = cfg.get("webhooks", [])
    hooks.append(hook.model_dump())
    cfg["webhooks"] = hooks
    save_yaml(config_path, cfg)
    store.config.webhooks.append(hook)
    return hook.model_dump()


@router.delete("/webhooks/{idx}", tags=["webhooks"])
def delete_webhook(idx: int, store: Store = Depends(get_store)):
    if idx < 0 or idx >= len(store.config.webhooks):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Webhook index {idx} not found"})
    store.config.webhooks.pop(idx)
    config_path = store.root / ".reqtool" / "config.yaml"
    cfg = load_yaml(config_path) if config_path.exists() else {}
    cfg["webhooks"] = [w.model_dump() for w in store.config.webhooks]
    save_yaml(config_path, cfg)
    return {"deleted": idx}


@router.get("/diff", tags=["diff"])
def diff_versions(
    v1: Optional[str] = None,
    v2: Optional[str] = "HEAD",
    since: Optional[str] = None,
    uid: Optional[str] = None,
    store: Store = Depends(get_store),
):
    from reqtool.git_ops import git_diff_tree
    ref_a = since or v1 or "HEAD~1"
    ref_b = v2 or "HEAD"
    return {
        "ref": ref_a,
        "target": ref_b,
        "changes": git_diff_tree(store.root, ref_a, ref_b),
    }


@router.post("/render/markdown", tags=["meta"])
def render_markdown(body: dict[str, Any]):
    text = body.get("text", "")
    import markdown
    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    return {"html": html}


@router.get("/hierarchy", tags=["hierarchy"])
def get_hierarchy(store: Store = Depends(get_store)):
    return {
        "types": {k: v.model_dump() for k, v in store.hierarchy.types.items()},
        "hierarchy": {k: v.model_dump() for k, v in store.hierarchy.hierarchy.items()},
        "workflows": {k: v.model_dump() for k, v in store.hierarchy.workflows.items()},
        "dor": store.hierarchy.dor,
        "dod": store.hierarchy.dod,
        "cross_layer_rules": [r.model_dump() for r in store.hierarchy.cross_layer_rules],
        "default_relationship_types": [r.model_dump() for r in store.hierarchy.default_relationship_types],
    }


@router.get("/hierarchy/types", tags=["hierarchy"])
def list_types(store: Store = Depends(get_store)):
    return {k: v.model_dump() for k, v in store.hierarchy.types.items()}


@router.get("/hierarchy/children/{req_type}", tags=["hierarchy"])
def allowed_children(req_type: str, store: Store = Depends(get_store)):
    return {"req_type": req_type, "allowed_children": store.get_allowed_children(req_type)}


@router.get("/kanban", tags=["kanban"])
def get_kanban(
    req_type: Optional[str] = None,
    iteration: Optional[str] = None,
    owner: Optional[str] = None,
    assignee: Optional[str] = None,
    store: Store = Depends(get_store),
):
    return store.build_kanban(
        req_type=req_type,
        iteration=iteration,
        owner=owner,
        assignee=assignee,
    )


@router.get("/filter-presets", tags=["filter-presets"])
def list_filter_presets(store: Store = Depends(get_store)):
    return store.list_filter_presets()


@router.put("/filter-presets/{preset_id}", tags=["filter-presets"])
def save_filter_preset(preset_id: str, body: dict, store: Store = Depends(get_store)):
    body["id"] = preset_id
    if not body.get("label"):
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "label is required"})
    return store.save_filter_preset(body)


@router.delete("/filter-presets/{preset_id}", tags=["filter-presets"])
def delete_filter_preset(preset_id: str, store: Store = Depends(get_store)):
    ok = store.delete_filter_preset(preset_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Preset '{preset_id}' not found"})
    return {"deleted": preset_id}


@router.get("/help", tags=["meta"])
def get_help(topic: Optional[str] = None, store: Store = Depends(get_store)):
    project_path = store.root / ".reqtool" / "help.yaml"
    default_path = Path(__file__).parent.parent / "defaults" / "help.yaml"
    for path in (project_path, default_path):
        if path.exists():
            data = load_yaml(path)
            if topic:
                return data.get(topic, {})
            return data
    return {}


@router.get("/badge/validated", tags=["meta"])
def validation_badge(store: Store = Depends(get_store)):
    result = validate_all(store)
    errors = result.get("errors", [])
    warnings = result.get("warnings", [])
    if errors:
        label = f"{len(errors)} error(s)"
        colour = "red"
    elif warnings:
        label = f"{len(warnings)} warning(s)"
        colour = "yellow"
    else:
        label = "passing"
        colour = "brightgreen"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="160" height="20">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <rect rx="3" width="160" height="20" fill="#555"/>
  <rect rx="3" x="80" width="80" height="20" fill="{colour}"/>
  <rect x="80" width="4" height="20" fill="{colour}"/>
  <rect rx="3" width="160" height="20" fill="url(#s)"/>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="110">
    <text x="405" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="630" lengthAdjust="spacing">validated</text>
    <text x="405" y="140" transform="scale(.1)" textLength="630" lengthAdjust="spacing">validated</text>
    <text x="1195" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="670" lengthAdjust="spacing">{label}</text>
    <text x="1195" y="140" transform="scale(.1)" textLength="670" lengthAdjust="spacing">{label}</text>
  </g>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@router.get("/metrics", tags=["metrics"])
def get_metrics(store: Store = Depends(get_store)):
    reqs = [r for r in store.requirements.values() if not r.get("deleted")]
    principles = [p for p in store.principles.values() if not p.get("deleted")]
    tbds = [t for t in store.tbds.values() if not t.get("deleted")]

    status_counts = Counter(r.get("status", "draft") for r in reqs)
    domain_counts = Counter(r.get("domain") or "unclassified" for r in reqs)
    priority_counts = Counter(r.get("priority", "medium") for r in reqs)

    no_owner = sum(1 for r in reqs if not r.get("owner"))
    no_ac = sum(1 for r in reqs if not r.get("acceptance_criteria"))
    no_rationale = sum(1 for r in reqs if not r.get("content", {}).get("rationale"))
    no_verification = sum(1 for r in reqs if r.get("verification", {}).get("status", "not_started") == "not_started")
    safety_related = sum(1 for r in reqs if r.get("safety_related"))
    open_tbds = sum(1 for t in tbds if t.get("status") in ("open", "in_progress"))

    approved = status_counts.get("approved", 0)
    in_review = status_counts.get("in_review", 0) + status_counts.get("reviewed", 0)
    draft = status_counts.get("draft", 0)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent_changes = 0
    for r in reqs:
        for h in r.get("history", []):
            try:
                dt_str = h.get("date", "")
                if dt_str:
                    dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
                    if dt > cutoff:
                        recent_changes += 1
            except Exception:
                pass

    asil_counts = Counter(r.get("asil_level") or r.get("safety_classification") or "non_safety" for r in reqs if r.get("safety_related"))

    return {
        "totals": {
            "requirements": len(reqs),
            "principles": len(principles),
            "tbds": len(tbds),
            "open_tbds": open_tbds,
            "safety_related": safety_related,
        },
        "status": dict(status_counts),
        "domain": dict(domain_counts),
        "priority": dict(priority_counts),
        "approval_funnel": {
            "draft": draft,
            "in_review": in_review,
            "approved": approved,
            "approval_rate_pct": round(approved / len(reqs) * 100, 1) if reqs else 0,
        },
        "quality_gaps": {
            "no_owner": no_owner,
            "no_ac": no_ac,
            "no_rationale": no_rationale,
            "not_verified": no_verification,
        },
        "velocity": {
            "changes_last_30d": recent_changes,
        },
        "widgets": [
            {"id": "w1", "type": "funnel", "title": "Approval Burndown", "data": {"approved": approved, "draft": draft, "in_review": in_review}},
            {"id": "w2", "type": "safety", "title": "ASIL Safety Classification", "data": dict(asil_counts)},
            {"id": "w3", "type": "gaps", "title": "Requirement Quality Gaps", "data": {"no_owner": no_owner, "no_ac": no_ac, "not_verified": no_verification}},
        ],
    }


@router.get("/workflow", tags=["workflow"])
def get_workflow(store: Store = Depends(get_store)):
    return store.config.workflow.model_dump()


@router.put("/workflow", tags=["workflow"])
def update_workflow(body: dict[str, Any], store: Store = Depends(get_store)):
    config_path = store.root / ".reqtool" / "config.yaml"
    config_data = load_yaml(config_path) if config_path.exists() else {}
    config_data["workflow"] = body
    save_yaml(config_path, config_data)
    store.config.workflow = WorkflowConfig.model_validate(body)
    return store.config.workflow.model_dump()


@router.get("/templates", tags=["templates"])
def list_templates(store: Store = Depends(get_store)):
    project_path = store.root / ".reqtool" / "templates.yaml"
    default_path = Path(__file__).parent.parent / "defaults" / "templates.yaml"
    for path in (project_path, default_path):
        if path.exists():
            data = load_yaml(path)
            if isinstance(data, list):
                return data
    return []


@router.put("/templates", tags=["templates"])
def save_templates(body: list[dict[str, Any]], store: Store = Depends(get_store)):
    save_yaml(store.root / ".reqtool" / "templates.yaml", body)
    return {"saved": len(body)}
