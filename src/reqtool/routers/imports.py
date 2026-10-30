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
from fastapi.responses import JSONResponse

from reqtool.store import Store
from pathlib import Path
from reqtool.git_ops import dirty_paths, git_list_tags, git_create_tag, git_diff_tree, git_show_file
from reqtool.identity import MissingIdentity, for_action, git_env
from reqtool.fileio import load_yaml as _load_yaml
from .deps import get_store, publish_event
from .auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/import/csv", status_code=201, tags=["import"])
async def import_csv(file: bytes = None, body: dict[str, Any] = None):
    raise HTTPException(status_code=501, detail={"error": "use_multipart",
        "message": "POST CSV as multipart/form-data file field 'file'"})


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace(".", "_")


def _parse_csv_rows(raw: bytes) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Decode and normalise a CSV body. Returns (rows, structural errors)."""
    try:
        text = raw.decode("utf-8-sig")
    except Exception:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    rows, errors = [], []
    width = len(reader.fieldnames or [])
    for i, row in enumerate(reader):
        if None in row:  # more cells than headers
            errors.append({"row": i + 1, "id": (row.get("id") or "?"), "error": f"row has more than the {width} columns in the header"})
            rows.append({})
            continue
        if any(v is None for v in row.values()):  # fewer cells than headers
            errors.append({"row": i + 1, "id": (row.get("id") or "?"), "error": f"row has fewer than the {width} columns in the header"})
            rows.append({})
            continue
        rows.append({_norm(k): v.strip() for k, v in row.items() if v and v.strip()})
    return rows, errors


def _row_fields(i: int, normed: dict[str, str]) -> dict[str, Any]:
    return {
        "id":     normed.get("id", f"IMP-{i+1:04d}"),
        "title":  normed.get("title", ""),
        "status": normed.get("status"),
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


def _validate_rows(store: Store, rows: list[dict[str, str]], keep_status: bool) -> tuple[list[tuple[int, dict, str]], list[dict]]:
    """Check every row before anything is written. Returns ([(index, fields, parent_ref)], errors)."""
    from reqtool.fileio import validate_id, InvalidId
    plan, errors, seen_ids = [], [], set()
    existing_ids = {r.get("id") for r in store.requirement_map().values() if not r.get("deleted")}
    for i, normed in enumerate(rows):
        if not normed:
            continue  # structural error already reported
        fields = _row_fields(i, normed)
        rid = fields["id"]

        def bad(msg: str) -> None:
            errors.append({"row": i + 1, "id": rid, "error": msg})

        if not fields["title"]:
            bad("title is required"); continue
        try:
            validate_id(rid, "id")
        except InvalidId as exc:
            bad(str(exc)); continue
        if rid in seen_ids:
            bad(f"ID '{rid}' appears more than once in the file"); continue
        if rid in existing_ids:
            bad(f"ID '{rid}' already exists in the repository"); continue
        seen_ids.add(rid)
        wf = store.get_workflow_for_type(fields["req_type"])
        requested = fields.pop("status")
        if requested and keep_status:
            if wf and requested not in [st.id for st in wf.states]:
                bad(f"status '{requested}' is not a state of the '{fields['req_type']}' workflow"); continue
            fields["status"] = requested
        # otherwise the item starts in the workflow's initial state and must be reviewed normally
        plan.append((i, fields, normed.get("parentid") or normed.get("parent_id") or ""))
    ids_in_file = {f["id"] for _, f, _ in plan}
    for i, fields, parent_ref in plan:
        if parent_ref and parent_ref not in ids_in_file and parent_ref not in existing_ids:
            errors.append({"row": i + 1, "id": fields["id"], "error": f"parent '{parent_ref}' not found in the file or the repository"})
    return plan, errors


@router.post("/import/csv/upload", status_code=201, tags=["import"])
async def import_csv_upload(
    request: Request,
    dry_run: bool = False,
    keep_status: bool = False,
    store: Store = Depends(get_store),
    user: dict = Depends(get_current_user),
):
    """Import requirements from CSV, all or nothing.

    Every row is validated first. If any row is invalid nothing is written and the
    response is ``422`` with a per-row error list. ``dry_run=true`` validates only.
    Imported items start in their workflow's initial state; ``keep_status=true``
    (administrators) keeps a valid ``status`` column instead.
    """
    if keep_status and user["authenticated"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "keep_status requires the admin role"})
    raw = await request.body()
    rows, errors = _parse_csv_rows(raw)
    plan, row_errors = _validate_rows(store, rows, keep_status)
    errors += row_errors
    if errors:
        errors.sort(key=lambda e: e["row"])
        raise HTTPException(status_code=422, detail={
            "error": "import_failed", "message": f"{len(errors)} row(s) invalid; nothing was imported",
            "errors": errors})
    if dry_run:
        return JSONResponse(status_code=200, content={"dry_run": True, "valid": len(plan), "imported": 0, "errors": [], "uids": []})

    created: list[str] = []
    with store.lock:  # nothing else may write while the batch is applied or rolled back
        try:
            id_to_uid: dict[str, str] = {}
            for i, fields, _ in plan:
                req = store.create_requirement(fields)
                id_to_uid[fields["id"]] = req["uid"]
                created.append(req["uid"])
            for i, fields, parent_ref in plan:
                if parent_ref:
                    parent_uid = id_to_uid.get(parent_ref) or store.resolve_uid(parent_ref)
                    store.update_requirement(id_to_uid[fields["id"]], {"parentId": parent_uid}, summary="Import: set parent")
        except Exception as exc:
            for uid in created:  # roll back: remove files and in-memory entries
                try:
                    store.req_path(uid).unlink(missing_ok=True)
                finally:
                    store.forget_requirement(uid)
            raise HTTPException(status_code=422, detail={
                "error": "import_failed", "message": f"Import rolled back: {exc}",
                "errors": [{"row": 0, "id": "", "error": str(exc)}]})
    for uid in created:
        publish_event(store, "requirement_created", {"uid": uid, "id": store.requirement_map()[uid].get("id")})
    return {"imported": len(created), "errors": [], "uids": created}


BASELINE_DIRS = ("requirements", "principles", "tbds", "decisions", "modules", "products")


def _describe_dirty(store: Store, paths: list[str]) -> list[str]:
    """Human IDs for changed artefact files (falls back to the file path)."""
    out = []
    for rel in paths:
        stem = Path(rel).stem
        item = (store.requirement_map().get(stem) or store.principle_map().get(stem)
                or store.decision_map().get(stem) or store.module_map().get(stem))
        out.append((item or {}).get("id") or rel)
    return sorted(set(out))


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
    try:
        who = for_action(store)
    except MissingIdentity as exc:
        raise HTTPException(status_code=409, detail={"error": "no_git_identity", "message": str(exc)})
    # A tag points at HEAD, so uncommitted edits would silently be left out of the baseline.
    dirty = dirty_paths(store.root, BASELINE_DIRS)
    uncommitted = _describe_dirty(store, dirty)
    if uncommitted and not body.get("allow_dirty"):
        raise HTTPException(status_code=409, detail={
            "error": "dirty_working_tree",
            "message": "Commit these changes first (or pass allow_dirty: true): " + ", ".join(uncommitted),
            "uncommitted": uncommitted})
    if uncommitted:
        message += "\n\nCreated with uncommitted changes not included in this baseline: " + ", ".join(uncommitted)
    try:
        sha = git_create_tag(store.root, tag, message, env=git_env(who, committer=who.author))
        return {"tag": tag, "sha": sha, "name": name, "message": message, "uncommitted": uncommitted}
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

