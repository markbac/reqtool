"""
reqtool.routers.system
======================
FastAPI router for system, config, metadata, hierarchy, kanban, metrics, workflow, help, and template endpoints.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional
from collections import Counter
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from reqtool import __version__
from reqtool.store import Store
from reqtool.validation import validate_all
from reqtool.repo_init import write_base_repo, write_enums
from reqtool.watcher import restart_watcher
from reqtool.fileio import load_yaml, save_yaml
from reqtool.models import RepoEnums, WorkflowConfig
from .deps import get_store

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", tags=["meta"])
def health(store: Store = Depends(get_store)):
    return {"status": "ok", "version": __version__, "requirements": len(store.requirement_map())}


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


def _validated(model, data):
    """Validate ``data`` against a pydantic model, mapping failure to HTTP 422."""
    from pydantic import ValidationError
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={
            "error": "validation",
            "message": "Invalid configuration: " + "; ".join(
                f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]),
        })


REDACTED = "********"


def _redact_hook(hook: dict[str, Any]) -> dict[str, Any]:
    out = dict(hook)
    out["has_secret"] = bool(out.get("secret"))
    if out.get("secret"):
        out["secret"] = REDACTED
    return out


def redact_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a config dump that is safe to send to a client."""
    out = dict(cfg)
    if isinstance(out.get("webhooks"), list):
        out["webhooks"] = [_redact_hook(h) for h in out["webhooks"]]
    return out


def _restore_redacted_secrets(incoming: dict[str, Any], current_hooks: list[dict[str, Any]]) -> None:
    """If a client echoes back the redacted placeholder, keep the stored secret."""
    hooks = incoming.get("webhooks")
    if not isinstance(hooks, list):
        return
    by_url = {h.get("url"): h.get("secret") for h in current_hooks}
    for h in hooks:
        if isinstance(h, dict):
            h.pop("has_secret", None)
            if h.get("secret") == REDACTED:
                h["secret"] = by_url.get(h.get("url"))


@router.get("/config", tags=["meta"])
def get_config(store: Store = Depends(get_store)):
    return redact_config(store.config.model_dump())


def _unknown_keys(model: Any, data: Any, prefix: str = "") -> list[str]:
    """Dotted paths in ``data`` that are not fields of the pydantic ``model`` (recursing into models and lists of models)."""
    import typing
    from pydantic import BaseModel
    if not (isinstance(model, type) and issubclass(model, BaseModel)) or not isinstance(data, dict):
        return []
    bad = []
    for key, value in data.items():
        field = model.model_fields.get(key)
        if field is None:
            bad.append(prefix + key)
            continue
        ann = field.annotation
        if typing.get_origin(ann) is list and isinstance(value, list):
            inner = typing.get_args(ann)[0]
            for i, item in enumerate(value):
                bad += _unknown_keys(inner, item, f"{prefix}{key}[{i}].")
        else:
            bad += _unknown_keys(ann, value, f"{prefix}{key}.")
    return bad


@router.put("/config", tags=["meta"])
def update_config(body: dict[str, Any], store: Store = Depends(get_store)):
    from reqtool.models import RepoConfig
    for hook in body.get("webhooks") or []:
        if isinstance(hook, dict):
            hook.pop("has_secret", None)  # read-only marker added by GET /config
    unknown = _unknown_keys(RepoConfig, body)
    if unknown:
        raise HTTPException(status_code=422, detail={
            "error": "validation",
            "message": "Unknown configuration setting(s): " + ", ".join(sorted(unknown))})
    config_path = store.root / ".reqtool" / "config.yaml"
    cfg = load_yaml(config_path) if config_path.exists() else {}
    _restore_redacted_secrets(body, cfg.get("webhooks") or [])
    cfg.update(body)
    new_config = _validated(RepoConfig, cfg)  # validate BEFORE persisting
    save_yaml(config_path, cfg)
    store.config = new_config
    return redact_config(store.config.model_dump())



@router.get("/repo", tags=["meta"])
def get_repo_info(store: Store = Depends(get_store)):
    return {
        "path": str(store.root),
        "repo_id": store.config.repo_id,
        "repo_title": store.config.repo_title,
        "repo_description": store.config.repo_description,
        "requirements_count": len(store.requirement_map()),
        "principles_count": len(store.principle_map()),
        "tbds_count": len(store.live_tbds()),
        "decisions_count": len(store.live_decision_records()),
    }


_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _authorise_repo_path(request: Request, raw_path: str) -> Path:
    """Gate for endpoints that let the caller pick a filesystem location.

    - Disabled entirely when REQTOOL_DISABLE_REPO_SWITCH=1.
    - Only accepted from a loopback client (a remote caller must never choose
      server filesystem paths).
    - If REQTOOL_REPO_ROOTS (os.pathsep-separated) is set, the resolved target
      must lie inside one of those directories.
    """
    if os.environ.get("REQTOOL_DISABLE_REPO_SWITCH") == "1":
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Repository switching is disabled"})
    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Repository switching is only allowed from the local machine"})
    target = Path(str(raw_path)).expanduser().resolve()
    roots = [r for r in os.environ.get("REQTOOL_REPO_ROOTS", "").split(os.pathsep) if r.strip()]
    if roots and not any(target.is_relative_to(Path(r).expanduser().resolve()) for r in roots):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Path is outside the allowed repository roots"})
    return target


@router.post("/repo/switch", tags=["meta"])
def switch_repo(body: dict[str, Any], request: Request, store: Store = Depends(get_store)):
    raw_path = body.get("path")
    if not raw_path:
        raise HTTPException(status_code=400, detail="path parameter required")
    target_path = _authorise_repo_path(request, raw_path)
    if not target_path.exists() or not (target_path / ".reqtool" / "config.yaml").exists():
        raise HTTPException(status_code=404, detail=f"No valid reqtool repository found at '{target_path}'")
    store.root = target_path
    store.load()
    restart_watcher(request.app, store)
    return get_repo_info(store)


@router.post("/repo/init", status_code=201, tags=["meta"])
def init_repo(body: dict[str, Any], request: Request, store: Store = Depends(get_store)):
    raw_path = body.get("path")
    if not raw_path:
        raise HTTPException(status_code=400, detail="path parameter required")
    target_path = _authorise_repo_path(request, raw_path)
    target_path.mkdir(parents=True, exist_ok=True)

    repo_id = body.get("repo_id") or target_path.name
    title = body.get("title") or repo_id.replace("-", " ").title()
    mode = body.get("mode", "defaults")

    if (target_path / ".reqtool" / "config.yaml").exists():
        raise HTTPException(status_code=409, detail=f"Repository already initialised at '{target_path}'")

    write_base_repo(target_path, repo_id, title)

    if mode == "defaults":
        defaults_dir = Path(__file__).parent.parent / "defaults"
        if (defaults_dir / "enums.yaml").exists():
            save_yaml(target_path / ".reqtool" / "enums.yaml", load_yaml(defaults_dir / "enums.yaml"))
        if (defaults_dir / "workflow.yaml").exists():
            cfg_p = target_path / ".reqtool" / "config.yaml"
            cfg = load_yaml(cfg_p) or {}
            cfg["workflow"] = load_yaml(defaults_dir / "workflow.yaml")
            save_yaml(cfg_p, cfg)
        if (defaults_dir / "hierarchy.yaml").exists():
            save_yaml(target_path / ".reqtool" / "hierarchy.yaml", load_yaml(defaults_dir / "hierarchy.yaml"))
        if (defaults_dir / "templates.yaml").exists():
            save_yaml(target_path / ".reqtool" / "templates.yaml", load_yaml(defaults_dir / "templates.yaml"))

        store.root = target_path
        store.load()

        if (defaults_dir / "principles.yaml").exists():
            p_data = load_yaml(defaults_dir / "principles.yaml")
            principles_list = p_data if isinstance(p_data, list) else p_data.get("principles", [])
            for p in principles_list:
                store.create_principle({
                    "id": p.get("id", ""),
                    "title": p.get("title", ""),
                    "domain": p.get("domain"),
                    "content": {
                        "description": p.get("description", ""),
                        "rationale": p.get("rationale", ""),
                        "implications": p.get("implications", ""),
                        "exceptions": p.get("exceptions", ""),
                    },
                })
    else:
        write_enums(target_path, domains=[])
        store.root = target_path
        store.load()

    restart_watcher(request.app, store)
    return get_repo_info(store)



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
    enums = _validated(RepoEnums, body)
    enums_path = store.root / ".reqtool" / "enums.yaml"
    save_yaml(enums_path, body)
    store.repo_enums = enums
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
    return [_redact_hook(w.model_dump()) for w in store.config.webhooks]


@router.post("/webhooks", status_code=201, tags=["webhooks"])
def add_webhook(body: dict[str, Any], store: Store = Depends(get_store)):
    from reqtool.models import WebhookConfig
    hook = WebhookConfig.model_validate(body)
    config_path = store.root / ".reqtool" / "config.yaml"
    cfg = load_yaml(config_path) if config_path.exists() else {}
    hooks = cfg.get("webhooks", [])
    hooks.append(hook.model_dump())
    cfg["webhooks"] = hooks
    # Update memory before the file: saving makes the watcher reload the config from disk, and appending
    # after that reload would list the hook twice.
    store.config.webhooks.append(hook)
    save_yaml(config_path, cfg)
    return _redact_hook(hook.model_dump())


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
    import nh3
    html = markdown.markdown(str(text), extensions=["tables", "fenced_code"])
    # Markdown passes raw HTML through; strip scripts, event handlers and
    # javascript: URLs before the result is placed in the DOM.
    return {"html": nh3.clean(html)}


@router.get("/hierarchy", tags=["hierarchy"])
def get_hierarchy(store: Store = Depends(get_store)):
    return {
        "types": {k: v.model_dump() for k, v in store.hierarchy.types.items()},
        "hierarchy": {k: v.model_dump() for k, v in store.hierarchy.hierarchy.items()},
        "workflows": {k: v.model_dump() for k, v in store.hierarchy.workflows.items()},
        "dor": store.hierarchy.dor,
        "dod": store.hierarchy.dod,
        "type_fields": store.hierarchy.type_fields,
        "cross_layer_rules": [r.model_dump() for r in store.hierarchy.cross_layer_rules],
        "default_relationship_types": [r.model_dump() for r in store.hierarchy.default_relationship_types],
        "enforce": store.hierarchy.enforce,
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
    reqs = store.live_requirements()
    principles = store.live_principles()
    tbds = store.live_tbds()

    status_counts = Counter(r.get("status", "draft") for r in reqs)
    domain_counts = Counter(r.get("domain") or "unclassified" for r in reqs)
    priority_counts = Counter(r.get("priority", "medium") for r in reqs)

    no_owner = sum(1 for r in reqs if not r.get("owner"))
    no_ac = sum(1 for r in reqs if not r.get("acceptance_criteria"))
    no_rationale = sum(1 for r in reqs if not (r.get("content") or {}).get("rationale"))
    no_verification = sum(1 for r in reqs if (r.get("verification") or {}).get("status", "not_started") == "not_started")
    safety_related = sum(1 for r in reqs if r.get("safety_related"))
    open_tbds = sum(1 for t in tbds if t.get("status") in ("open", "in_progress"))
    suspect_links = sum(1 for r in reqs for rel in r.get("relationships") or [] if rel.get("suspect"))

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
            "suspect_links": suspect_links,
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
    workflow = _validated(WorkflowConfig, body)
    config_data["workflow"] = body
    from reqtool.models import RepoConfig
    _validated(RepoConfig, config_data)  # the whole file must still load on restart
    save_yaml(config_path, config_data)
    store.config.workflow = workflow
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


import subprocess
import shutil

PLANTUML_MAX_BYTES = 100_000
# Directives that read local files or fetch URLs. PlantUML's SANDBOX profile blocks
# them as well; this rejects them up front with a clear message.
_PLANTUML_FORBIDDEN = re.compile(r"^\s*!(include\w*|import|theme\b[^\n]*\bfrom\b)", re.IGNORECASE | re.MULTILINE)


@router.post("/render/plantuml", tags=["meta"])
def render_plantuml(body: dict[str, Any], store: Store = Depends(get_store)):
    """Render PlantUML code to SVG using a backend plantuml.jar or java process."""
    raw_text = body.get("text", "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="PlantUML text payload required")

    if len(raw_text.encode("utf-8")) > PLANTUML_MAX_BYTES:
        raise HTTPException(status_code=413, detail={"error": "too_large",
                            "message": f"PlantUML source is limited to {PLANTUML_MAX_BYTES} bytes"})
    if _PLANTUML_FORBIDDEN.search(raw_text):
        raise HTTPException(status_code=422, detail={"error": "validation",
                            "message": "PlantUML !include, !import and !theme-from directives are not allowed"})

    if not raw_text.startswith("@start"):
        text = f"@startuml\n{raw_text}\n@enduml"
    else:
        text = raw_text

    # Locate plantuml.jar
    jar_candidates = [
        os.environ.get("PLANTUML_JAR"),
        str(store.root / ".reqtool" / "plantuml.jar"),
        str(Path(__file__).parent.parent / "defaults" / "plantuml.jar"),
        "plantuml.jar",
    ]
    jar_path = next((c for c in jar_candidates if c and Path(c).exists()), None)

    java_bin = shutil.which("java")

    if jar_path and java_bin:
        try:
            res = subprocess.run(
                [java_bin, "-jar", jar_path, "-pipe", "-tsvg"],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=15,
                env={**os.environ, "PLANTUML_SECURITY_PROFILE": "SANDBOX"},
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PlantUML execution failed: {exc}")
        if res.returncode == 0 and res.stdout:
            return Response(content=res.stdout.decode("utf-8"), media_type="image/svg+xml")
        err_msg = res.stderr.decode("utf-8", errors="replace") if res.stderr else "PlantUML error"
        raise HTTPException(status_code=400, detail=f"PlantUML render error: {err_msg}")

    # Fallback response explaining how to enable plantuml.jar
    fallback_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="540" height="120" viewBox="0 0 540 120">
  <rect width="100%" height="100%" fill="#161b22" rx="8" stroke="#30363d"/>
  <text x="20" y="35" fill="#f0883e" font-family="monospace" font-size="13" font-weight="bold">PlantUML Backend Server Mode</text>
  <text x="20" y="65" fill="#c9d1d9" font-family="sans-serif" font-size="11">Place plantuml.jar in .reqtool/plantuml.jar or set PLANTUML_JAR env var.</text>
  <text x="20" y="90" fill="#8b949e" font-family="sans-serif" font-size="11">Java runtime requirement: java -jar plantuml.jar -pipe -tsvg</text>
</svg>"""
    return Response(content=fallback_svg, media_type="image/svg+xml")
