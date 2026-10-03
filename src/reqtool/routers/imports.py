"""
reqtool.routers.imports
=======================
FastAPI router for CSV imports and baseline management.
"""

from __future__ import annotations

import csv
import io
import logging
import ruamel.yaml as ry
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request

from reqtool.store import Store
from reqtool.git_ops import git_list_tags, git_create_tag, ensure_git_config, git_diff_tree, git_show_file
from reqtool.fileio import load_yaml as _load_yaml
from .deps import get_store

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/import/csv", status_code=201, tags=["import"])
async def import_csv(file: bytes = None, body: dict[str, Any] = None):
    raise HTTPException(status_code=501, detail={"error": "use_multipart",
        "message": "POST CSV as multipart/form-data file field 'file'"})


@router.post("/import/csv/upload", status_code=201, tags=["import"])
async def import_csv_upload(request: Request, store: Store = Depends(get_store)):
    raw = await request.body()
    try:
        text = raw.decode("utf-8-sig")
    except Exception:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    def _norm(name: str) -> str:
        return name.strip().lower().replace(" ", "_").replace(".", "_")

    created = []
    errors = []
    id_to_uid: dict[str, str] = {}

    rows = list(reader)
    for i, row in enumerate(rows):
        normed = {_norm(k): v.strip() for k, v in row.items() if v and v.strip()}
        try:
            fields: dict[str, Any] = {
                "id":     normed.get("id", f"IMP-{i+1:04d}"),
                "title":  normed.get("title", ""),
                "status": normed.get("status", "draft"),
                "priority": normed.get("priority", "medium"),
                "req_type": normed.get("req_type") or normed.get("type", "functional"),
                "domain":  normed.get("domain"),
                "owner":   normed.get("owner"),
                "discipline": normed.get("discipline"),
                "component": normed.get("component"),
                "verification_method": normed.get("verification_method"),
                "safety_related": normed.get("safety_related", "").lower() in ("true", "1", "yes"),
                "content": {
                    "description": normed.get("content_description") or normed.get("description", ""),
                    "rationale":   normed.get("content_rationale") or normed.get("rationale", ""),
                    "extended_description": normed.get("extended_description", ""),
                },
                "tags": [t.strip() for t in normed.get("tags", "").split(";") if t.strip()],
                "allocated_to": [t.strip() for t in normed.get("allocated_to", "").split(";") if t.strip()],
            }
            if not fields["title"]:
                errors.append({"row": i+1, "error": "title is required"})
                continue
            fields.pop("parentId", None)
            req = store.create_requirement(fields)
            id_to_uid[fields["id"]] = req["uid"]
            created.append(req["uid"])
        except Exception as exc:
            errors.append({"row": i+1, "id": normed.get("id", "?"), "error": str(exc)})

    for i, row in enumerate(rows):
        normed = {_norm(k): v.strip() for k, v in row.items() if v and v.strip()}
        req_id = normed.get("id", f"IMP-{i+1:04d}")
        parent_ref = normed.get("parentid") or normed.get("parent_id") or normed.get("parentid", "")
        if parent_ref and req_id in id_to_uid:
            parent_uid = id_to_uid.get(parent_ref)
            if parent_uid:
                store.update_requirement(id_to_uid[req_id], {"parentId": parent_uid}, summary="Import: set parent")

    return {"imported": len(created), "errors": errors, "uids": created}


@router.get("/baselines", tags=["baselines"])
def list_baselines(store: Store = Depends(get_store)):
    return git_list_tags(store.root, prefix="baseline/")


@router.post("/baselines", status_code=201, tags=["baselines"])
def create_baseline(body: dict[str, Any], store: Store = Depends(get_store)):
    name = body.get("name", "").strip().replace(" ", "-")
    if not name:
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "name is required"})
    tag = f"baseline/{name}"
    message = body.get("message", f"Baseline: {name}")
    ensure_git_config(store.root, store.config.git.commit_name, store.config.git.commit_email)
    try:
        sha = git_create_tag(store.root, tag, message)
        return {"tag": tag, "sha": sha, "name": name, "message": message}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})


@router.get("/baselines/{name}/diff", tags=["baselines"])
def baseline_diff(name: str, store: Store = Depends(get_store)):
    tag = f"baseline/{name}"
    _require_tag(store, tag)
    changes = git_diff_tree(store.root, tag)
    req_changes = [c for c in changes if c["path"].startswith("requirements/") and c["path"].endswith(".yaml")]

    result = {"baseline": tag, "added": [], "removed": [], "changed": []}
    for change in req_changes:
        status = change["status"]
        path = store.root / change["path"]
        if status == "A":
            current = None
            try:
                current = _load_yaml(path)
            except Exception:
                pass
            result["added"].append({"id": current.get("id", "?") if current else "?", "path": change["path"]})
        elif status == "D":
            old_content = git_show_file(store.root, tag, store.root / change["path"])
            if old_content:
                try:
                    yml = ry.YAML()
                    old = yml.load(old_content)
                    result["removed"].append({"id": old.get("id", "?") if old else "?", "path": change["path"]})
                except Exception:
                    result["removed"].append({"path": change["path"]})
        elif status in ("M", "R"):
            current = None
            try:
                current = _load_yaml(path)
            except Exception:
                pass
            result["changed"].append({"id": current.get("id", "?") if current else "?", "path": change["path"]})

    return result


def _require_tag(store: Store, tag: str) -> None:
    if tag not in {t["name"] for t in git_list_tags(store.root, prefix="baseline/")}:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Baseline '{tag}' not found"})


@router.get("/baselines/compare", tags=["baselines"])
def compare_two_baselines(baseline_a: str, baseline_b: str, store: Store = Depends(get_store)):
    tag_a = f"baseline/{baseline_a}" if not baseline_a.startswith("baseline/") else baseline_a
    tag_b = f"baseline/{baseline_b}" if not baseline_b.startswith("baseline/") else baseline_b

    _require_tag(store, tag_a)
    _require_tag(store, tag_b)
    changes = git_diff_tree(store.root, tag_a, tag_b)
    req_changes = [c for c in changes if c["path"].startswith("requirements/") and c["path"].endswith(".yaml")]

    result = {
        "baseline_a": tag_a,
        "baseline_b": tag_b,
        "summary": {"added": 0, "removed": 0, "modified": 0},
        "added": [],
        "removed": [],
        "modified": [],
    }

    for change in req_changes:
        status = change["status"]
        path = change["path"]
        if status == "A":
            result["summary"]["added"] += 1
            result["added"].append({"path": path, "status": "added"})
        elif status == "D":
            result["summary"]["removed"] += 1
            result["removed"].append({"path": path, "status": "removed"})
        elif status in ("M", "R"):
            result["summary"]["modified"] += 1
            result["modified"].append({"path": path, "status": "modified"})

    return result

