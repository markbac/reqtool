"""
reqtool.api
===========
FastAPI application. All endpoints from spec §9.
OpenAPI 3.1 spec is generated automatically at GET /openapi.json.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .store import Store
from .validation import validate_all, validate_single
from .exports import export_markdown_zip, export_csv, export_jsx
from .git_ops import (
    is_git_repo, has_conflicts, git_status, stage_file, commit as git_commit,
    git_log, ensure_git_config,
)
from .models import (
    CommitRequest, ApproveRequest, ResolveRequest, BulkUpdateRequest,
    CreateRequirementRequest, UpdateRequirementRequest,
    CreatePrincipleRequest, UpdatePrincipleRequest,
    CreateTBDRequest, UpdateTBDRequest,
    AddACRequest, UpdateACRequest,
    ExportRequest, ExportMarkdownRequest, ExportCSVRequest,
)
from .fileio import utcnow_iso, uuid7

log = logging.getLogger(__name__)


def create_app(repo_root: Path) -> FastAPI:
    store = Store(repo_root)
    store.load()

    app = FastAPI(
        title="reqtool",
        version=__version__,
        description=(
            "Git-backed YAML requirements management tool. "
            "Requirements, principles, and TBDs live as individual YAML files; "
            "the API handles hashing, versioning, validation, and export."
        ),
        license_info={"name": "MIT"},
        contact={"name": "reqtool"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # File watcher to reload on external changes
    # ------------------------------------------------------------------

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class ReloadHandler(FileSystemEventHandler):
            def on_any_event(self, event):
                if event.is_directory:
                    return
                if event.src_path.endswith(".yaml"):
                    changed = Path(event.src_path)
                    log.debug("File changed: %s", changed)
                    store.reload_file(changed)

        observer = Observer()
        for subdir in ("requirements", "principles", "tbds", "modules", "products", ".reqtool"):
            watch_path = repo_root / subdir
            watch_path.mkdir(parents=True, exist_ok=True)
            observer.schedule(ReloadHandler(), str(watch_path), recursive=True)
        observer.start()
        log.info("File watcher started (incremental reload)")
    except Exception as exc:
        log.warning("File watcher not started: %s", exc)

    def _fire_webhook(store: "Store", event: str, payload: dict) -> None:
        """Fire webhooks async (best-effort, non-blocking)."""
        import threading
        hooks = [w for w in store.config.webhooks if w.enabled and event in w.events]
        if not hooks:
            return
        import json as _json
        body = _json.dumps({
            "event": event,
            "repo_id": store.config.repo_id,
            "payload": payload,
        }).encode()
        def _send(url: str, secret: Optional[str]) -> None:
            try:
                import httpx, hashlib, hmac
                headers = {"Content-Type": "application/json", "X-Reqtool-Event": event}
                if secret:
                    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                    headers["X-Reqtool-Signature"] = f"sha256={sig}"
                httpx.post(url, content=body, headers=headers, timeout=5)
            except Exception as exc:
                log.warning("Webhook delivery failed to %s: %s", url, exc)
        for hook in hooks:
            threading.Thread(target=_send, args=(hook.url, hook.secret), daemon=True).start()

    # ------------------------------------------------------------------
    # WebSocket manager for real-time updates
    # ------------------------------------------------------------------
    import asyncio

    class ConnectionManager:
        def __init__(self):
            self.active: list[WebSocket] = []

        async def connect(self, ws: WebSocket):
            await ws.accept()
            self.active.append(ws)

        def disconnect(self, ws: WebSocket):
            if ws in self.active:
                self.active.remove(ws)

        async def broadcast(self, message: dict):
            import json as _json
            text = _json.dumps(message)
            dead = []
            for ws in list(self.active):
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(ws)

    ws_manager = ConnectionManager()

    def _broadcast_sync(event: str, payload: dict) -> None:
        """Fire-and-forget WebSocket broadcast from sync context."""
        import threading, json as _json
        msg = {"event": event, **payload}
        async def _do():
            await ws_manager.broadcast(msg)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_do())
        except Exception:
            pass

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """Real-time event stream. Events: created, updated, deleted, status_changed."""
        await ws_manager.connect(websocket)
        try:
            while True:
                # Keep alive -- client may send pings
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    # Patch _fire_webhook to also broadcast via WS
    _orig_fire = _fire_webhook

    def _fire_all(store, event, payload):
        _orig_fire(store, event, payload)
        _broadcast_sync(event, {"uid": payload.get("uid", ""), "payload": payload})

    # Replace local reference
    _fire_webhook_local = _fire_all

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _not_found(uid: str) -> HTTPException:
        return HTTPException(status_code=404, detail={"error": "not_found", "message": f"UID '{uid}' not found", "uid": uid})

    def _conflict(msg: str) -> HTTPException:
        return HTTPException(status_code=409, detail={"error": "conflict", "message": msg})

    # ------------------------------------------------------------------
    # Requirements
    # ------------------------------------------------------------------

    @app.get("/requirements")
    def list_requirements(
        product: Optional[str] = None,
        domain: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        req_type: Optional[str] = None,
        owner: Optional[str] = None,
        tag: Optional[str] = None,
        deleted: bool = False,
    ):
        results = []
        for req in store.requirements.values():
            if not deleted and req.get("deleted"):
                continue
            if deleted and not req.get("deleted"):
                continue
            if domain and req.get("domain") != domain:
                continue
            if status and req.get("status") != status:
                continue
            if priority and req.get("priority") != priority:
                continue
            if req_type and req.get("req_type") != req_type:
                continue
            if owner and req.get("owner") != owner:
                continue
            if tag and tag not in req.get("tags", []):
                continue
            results.append({
                "uid": req.get("uid"),
                "id": req.get("id"),
                "title": req.get("title"),
                "status": req.get("status"),
                "priority": req.get("priority"),
                "req_type": req.get("req_type"),
                "domain": req.get("domain"),
                "owner": req.get("owner"),
                "version": req.get("version"),
                "parentId": req.get("parentId"),
            })
        return sorted(results, key=lambda r: r.get("id", ""))

    @app.get("/requirements/tree")
    def requirements_tree(
        product: str = Query(...),
        variant: Optional[str] = None,
    ):
        return store.build_tree(product, variant)

    @app.get("/requirements/{uid}")
    def get_requirement(uid: str):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        return req

    @app.post("/requirements/bulk")
    def bulk_update_requirements(body: BulkUpdateRequest):
        """Update a set of fields across multiple requirements at once."""
        updated = []
        failed = []
        for uid in body.uids:
            result = store.update_requirement(
                uid, body.fields,
                increment=body.increment,
                summary=body.summary,
            )
            if result:
                updated.append(uid)
            else:
                failed.append(uid)
        return {"updated": updated, "failed": failed, "count": len(updated)}

    @app.post("/requirements/{uid}/clone", status_code=201)
    def clone_requirement(uid: str, new_id: str = ""):
        """Duplicate a requirement, clearing history and resetting version."""
        src = store.get_requirement(uid)
        if src is None:
            raise _not_found(uid)
        import copy
        fields = copy.deepcopy(src)
        # Strip identity fields; backend will assign new uid/version/history
        for key in ("uid", "content_hash", "created", "last_modified", "history",
                    "version", "schema_version", "tool_version", "type"):
            fields.pop(key, None)
        if new_id:
            fields["id"] = new_id
        else:
            fields["id"] = src.get("id", "REQ") + "-COPY"
        fields["title"] = src.get("title", "") + " (copy)"
        fields["status"] = "draft"
        fields["approval"] = {"status": "draft", "approved_by": None, "approved_date": None}
        fields["verification"] = {"status": "not_started", "verified_date": None, "note": ""}
        return store.create_requirement(fields)

    @app.post("/requirements", status_code=201, tags=["requirements"])
    def create_requirement(body: CreateRequirementRequest):
        if has_conflicts(repo_root):
            raise _conflict("Working tree has unresolved merge conflicts")
        return store.create_requirement(body.model_dump(exclude_none=True))

    @app.put("/requirements/{uid}", tags=["requirements"])
    def update_requirement(uid: str, body: UpdateRequirementRequest, if_version: Optional[str] = None):
        """Update a requirement. Pass if_version=<current_version> to detect concurrent edits."""
        if has_conflicts(repo_root):
            raise _conflict("Working tree has unresolved merge conflicts")
        existing = store.get_requirement(uid)
        if existing is None:
            raise _not_found(uid)
        if if_version and existing.get("version") != if_version:
            raise HTTPException(status_code=409, detail={
                "error": "version_conflict",
                "message": f"Requirement was modified since you loaded it "
                           f"(your version: {if_version}, current: {existing.get('version')}). "
                           "Reload and re-apply your changes.",
                "current_version": existing.get("version"),
                "your_version": if_version,
            })
        old_status = existing.get("status")
        new_status = body.model_dump(exclude_none=True).get("status")
        if new_status and new_status != old_status:
            error = store.validate_transition(existing, new_status)
            if error:
                raise HTTPException(status_code=409, detail={"error": "workflow_guard", "message": error})
        result = store.update_requirement(uid, body.model_dump(exclude_none=True), summary="Updated via API")
        if result is None:
            raise _not_found(uid)
        if result.get("status") != old_status:
            _fire_webhook(store, "status_changed", {
                "uid": uid, "id": result.get("id"),
                "from": old_status, "to": result.get("status"),
            })
        return result

    @app.delete("/requirements/{uid}")
    def delete_requirement(uid: str):
        result = store.delete_requirement(uid)
        if result is None:
            raise _not_found(uid)
        return result

    @app.post("/requirements/{uid}/commit")
    def commit_requirement(uid: str, body: CommitRequest):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        if has_conflicts(repo_root):
            raise _conflict("Working tree has unresolved merge conflicts")
        try:
            file_path = store.req_path(uid)
            # Ensure version/hash are current before staging (spec §8.1 steps a-e)
            store.update_requirement(
                uid, {},
                increment=body.increment or "patch",
                summary=body.message or "Committed via UI",
                change_ref=body.change_ref,
            )
            stage_file(repo_root, file_path)
            sha = git_commit(
                repo_root, body.message,
                store.config.git.commit_name, store.config.git.commit_email,
            )
            # Write commit SHA back to the last history entry and re-save (spec §8.1 step h)
            req = store.get_requirement(uid)
            if req and req.get("history"):
                req["history"][-1]["commit_sha"] = sha[:7]
                from .fileio import save_yaml
                save_yaml(file_path, req)
            return {"commit_sha": sha, "version": req.get("version", "") if req else ""}
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})

    @app.post("/requirements/{uid}/approve")
    def approve_requirement(uid: str, body: ApproveRequest):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        now = utcnow_iso()
        result = store.update_requirement(uid, {
            "approval": {"status": "approved", "approved_by": body.approved_by, "approved_date": now},
            "status": "approved",
        }, increment="minor", summary=f"Approved by {body.approved_by}")
        _fire_webhook(store, "approved", {"uid": uid, "id": req.get("id"), "approved_by": body.approved_by})
        return result

    @app.get("/requirements/{uid}/history")
    def requirement_history(uid: str):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        file_path = store.req_path(uid)
        git_entries = git_log(repo_root, file_path)
        return {
            "in_file": req.get("history", []),
            "git": git_entries,
        }

    @app.get("/requirements/{uid}/relationships")
    def requirement_relationships(uid: str):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        outgoing = req.get("relationships", [])
        incoming = []
        for other_uid, other in store.requirements.items():
            if other_uid == uid:
                continue
            for rel in other.get("relationships", []):
                if rel.get("target", {}).get("uid") == uid:
                    incoming.append({"source_uid": other_uid, "source_id": other.get("id"), "type": rel.get("type")})
        return {"outgoing": outgoing, "incoming": incoming}

    # ------------------------------------------------------------------
    # Acceptance Criteria
    # ------------------------------------------------------------------

    @app.post("/requirements/{uid}/ac", status_code=201, tags=["requirements"])
    def add_ac(uid: str, body: AddACRequest):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        ac_uid = uuid7()
        new_ac = {
            "uid": ac_uid,
            "id": body.id or f"{req.get('id', '')}__AC-{ac_uid[:8]}",
            "text": body.text,
            "links": body.links or [],
        }
        acs = list(req.get("acceptance_criteria", []))
        acs.append(new_ac)
        return store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Added acceptance criterion")

    @app.put("/requirements/{uid}/ac/{ac_uid}", tags=["requirements"])
    def update_ac(uid: str, ac_uid: str, body: UpdateACRequest):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        acs = list(req.get("acceptance_criteria", []))
        for i, ac in enumerate(acs):
            if ac.get("uid") == ac_uid:
                acs[i] = {**ac, **body.model_dump(exclude_none=True)}
                return store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Updated acceptance criterion")
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"AC '{ac_uid}' not found"})

    @app.delete("/requirements/{uid}/ac/{ac_uid}")
    def delete_ac(uid: str, ac_uid: str):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        acs = [ac for ac in req.get("acceptance_criteria", []) if ac.get("uid") != ac_uid]
        return store.update_requirement(uid, {"acceptance_criteria": acs}, summary="Removed acceptance criterion")

    # ------------------------------------------------------------------
    # Principles
    # ------------------------------------------------------------------

    @app.get("/principles")
    def list_principles():
        return [p for p in store.principles.values() if not p.get("deleted")]

    @app.get("/principles/{uid}")
    def get_principle(uid: str):
        p = store.get_principle(uid)
        if p is None:
            raise _not_found(uid)
        return p

    @app.post("/principles", status_code=201, tags=["principles"])
    def create_principle(body: CreatePrincipleRequest):
        return store.create_principle(body.model_dump(exclude_none=True))

    @app.put("/principles/{uid}", tags=["principles"])
    def update_principle(uid: str, body: UpdatePrincipleRequest):
        result = store.update_principle(uid, body.model_dump(exclude_none=True), summary="Updated via API")
        if result is None:
            raise _not_found(uid)
        return result

    @app.delete("/principles/{uid}")
    def delete_principle(uid: str):
        result = store.delete_principle(uid)
        if result is None:
            raise _not_found(uid)
        return result

    @app.post("/principles/{uid}/commit")
    def commit_principle(uid: str, body: CommitRequest):
        p = store.get_principle(uid)
        if p is None:
            raise _not_found(uid)
        if has_conflicts(repo_root):
            raise _conflict("Working tree has unresolved merge conflicts")
        try:
            path = store.principle_path(uid)
            store.update_principle(uid, {}, increment=body.increment or "patch",
                                   summary=body.message or "Committed via UI", change_ref=body.change_ref)
            stage_file(repo_root, path)
            sha = git_commit(repo_root, body.message,
                             store.config.git.commit_name, store.config.git.commit_email)
            p = store.get_principle(uid)
            if p and p.get("history"):
                p["history"][-1]["commit_sha"] = sha[:7]
                from .fileio import save_yaml
                save_yaml(path, p)
            return {"commit_sha": sha, "version": p.get("version", "") if p else ""}
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})

    # ------------------------------------------------------------------
    # TBDs
    # ------------------------------------------------------------------

    @app.get("/tbds")
    def list_tbds(
        status: Optional[str] = None,
        priority: Optional[str] = None,
        owner: Optional[str] = None,
    ):
        results = []
        for tbd in store.tbds.values():
            if tbd.get("deleted"):
                continue
            if status and tbd.get("status") != status:
                continue
            if priority and tbd.get("priority") != priority:
                continue
            if owner and tbd.get("owner") != owner:
                continue
            t = dict(tbd)
            t["affected_requirements"] = store.compute_affected_requirements(tbd["uid"])
            results.append(t)
        return results

    @app.get("/tbds/{uid}")
    def get_tbd(uid: str):
        t = store.get_tbd(uid)
        if t is None:
            raise _not_found(uid)
        result = dict(t)
        result["affected_requirements"] = store.compute_affected_requirements(uid)
        return result

    @app.post("/tbds", status_code=201, tags=["tbds"])
    def create_tbd(body: CreateTBDRequest):
        return store.create_tbd(body.model_dump(exclude_none=True))

    @app.put("/tbds/{uid}", tags=["tbds"])
    def update_tbd(uid: str, body: UpdateTBDRequest):
        result = store.update_tbd(uid, body.model_dump(exclude_none=True), summary="Updated via API")
        if result is None:
            raise _not_found(uid)
        return result

    @app.delete("/tbds/{uid}")
    def delete_tbd(uid: str):
        result = store.delete_tbd(uid)
        if result is None:
            raise _not_found(uid)
        return result

    @app.post("/tbds/{uid}/commit")
    def commit_tbd(uid: str, body: CommitRequest):
        t = store.get_tbd(uid)
        if t is None:
            raise _not_found(uid)
        if has_conflicts(repo_root):
            raise _conflict("Working tree has unresolved merge conflicts")
        try:
            path = store.tbd_path(uid)
            store.update_tbd(uid, {}, increment=body.increment or "patch",
                             summary=body.message or "Committed via UI", change_ref=body.change_ref)
            stage_file(repo_root, path)
            sha = git_commit(repo_root, body.message,
                             store.config.git.commit_name, store.config.git.commit_email)
            t = store.get_tbd(uid)
            if t and t.get("history"):
                t["history"][-1]["commit_sha"] = sha[:7]
                from .fileio import save_yaml
                save_yaml(path, t)
            return {"commit_sha": sha, "version": t.get("version", "") if t else ""}
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})

    @app.post("/tbds/{uid}/resolve")
    def resolve_tbd(uid: str, body: ResolveRequest):
        t = store.get_tbd(uid)
        if t is None:
            raise _not_found(uid)
        now = utcnow_iso()
        content = dict(t.get("content", {}))
        content["resolution"] = body.resolution
        result = store.update_tbd(uid, {
            "status": "resolved",
            "content": content,
        }, increment="minor", summary=f"Resolved by {body.resolved_by}")
        return result

    # ------------------------------------------------------------------
    # Modules
    # ------------------------------------------------------------------

    @app.get("/modules")
    def list_modules():
        return list(store.modules.values())

    @app.get("/modules/{module_id}")
    def get_module(module_id: str):
        m = store.modules.get(module_id)
        if m is None:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Module '{module_id}' not found"})
        return {
            "manifest": m,
            "requirements": list(store.module_requirements.get(module_id, {}).values()),
        }

    @app.post("/modules/{module_id}/import")
    def import_module(module_id: str, product_id: str = ""):
        if not product_id:
            # Import for all products that reference this module
            results = []
            for pid, product in store.products.items():
                if any(m.get("id") == module_id for m in product.get("modules", [])):
                    lock = store.import_module(pid, module_id)
                    results.append({"product": pid, "locked": len(lock.get("locked", []))})
            if not results:
                raise HTTPException(status_code=404, detail={
                    "error": "not_found",
                    "message": f"Module '{module_id}' not referenced by any product"
                })
            return {"status": "ok", "results": results}
        try:
            lock = store.import_module(product_id, module_id)
            return {"status": "ok", "product": product_id, "module": module_id,
                    "locked_entries": len(lock.get("locked", []))}
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})

    @app.get("/modules/{module_id}/verify")
    def verify_module(module_id: str, product_id: str = ""):
        if not product_id:
            # Try first product that references this module
            for pid, product in store.products.items():
                if any(m.get("id") == module_id for m in product.get("modules", [])):
                    product_id = pid
                    break
        if not product_id:
            raise HTTPException(status_code=404, detail={
                "error": "not_found",
                "message": f"Module '{module_id}' not referenced by any product"
            })
        return store.verify_module(product_id, module_id)

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    @app.get("/products", tags=["products"])
    def list_products():
        return list(store.products.values())

    @app.post("/products", status_code=201, tags=["products"])
    def create_product(body: dict[str, Any]):
        """Create a new product manifest."""
        from .fileio import save_yaml, uuid7, utcnow_iso
        product_id = body.get("id", "").strip()
        if not product_id:
            raise HTTPException(status_code=422, detail={"error": "validation", "message": "id is required"})
        if product_id in store.products:
            raise HTTPException(status_code=409, detail={"error": "conflict", "message": f"Product '{product_id}' already exists"})
        prod_dir = repo_root / "products" / product_id
        prod_dir.mkdir(parents=True, exist_ok=True)
        now = utcnow_iso()
        product = {
            "schema_version": "1.0.0", "type": "product", "tool_version": "0.1.0",
            "uid": uuid7(), "id": product_id,
            "title": body.get("title", product_id),
            "version": "1.0.0",
            "content": body.get("content", {"description": ""}),
            "modules": [], "root_requirements": [], "display_order": [],
            "content_hash": "", "created": now, "last_modified": now, "history": [],
        }
        save_yaml(prod_dir / "_product.yaml", product)
        store.products[product_id] = product
        return product

    @app.get("/products/{product_id}")
    def get_product(product_id: str):
        p = store.products.get(product_id)
        if p is None:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Product '{product_id}' not found"})
        return p

    @app.get("/products/{product_id}/tree")
    def product_tree(product_id: str, variant: Optional[str] = None):
        return store.build_tree(product_id, variant)

    @app.get("/products/{product_id}/matrix")
    def product_matrix(product_id: str):
        """Allocation matrix: requirements x teams."""
        reqs = [r for r in store.requirements.values() if not r.get("deleted")]
        teams: set[str] = set()
        for req in reqs:
            for team in req.get("allocated_to", []):
                teams.add(team)
        matrix = []
        for req in sorted(reqs, key=lambda r: r.get("id", "")):
            row = {"uid": req["uid"], "id": req.get("id"), "title": req.get("title"), "teams": {}}
            for team in teams:
                row["teams"][team] = team in req.get("allocated_to", [])
            matrix.append(row)
        return {"teams": sorted(teams), "requirements": matrix}

    @app.get("/config", tags=["meta"])
    def get_config():
        return store.config.model_dump()

    @app.get("/version", tags=["meta"])
    def get_version():
        """Return tool version, schema version, and repo ID."""
        return {
            "tool_version": __version__,
            "schema_version": "1.0.0",
            "repo_id": store.config.repo_id,
            "repo_title": store.config.repo_title,
        }

    @app.get("/search", tags=["meta"])
    def search_uids(q: str = "", limit: int = 20):
        """Search requirements and principles by ID or title fragment."""
        if not q:
            return []
        return store.search_uids(q, limit)

    # ---------------------------------------------------------------------------
    # Enums
    # ---------------------------------------------------------------------------

    @app.get("/enums")
    def get_enums():
        return store.merged_enums()

    @app.get("/enums/core")
    def get_core_enums():
        return store.core_enums.model_dump()

    @app.get("/enums/repo")
    def get_repo_enums():
        return store.repo_enums.model_dump()

    @app.put("/enums/repo", tags=["enums"])
    def update_repo_enums(body: dict[str, Any]):
        from .fileio import save_yaml
        from .models import RepoEnums
        enums_path = repo_root / ".reqtool" / "enums.yaml"
        save_yaml(enums_path, body)
        store.repo_enums = RepoEnums.model_validate(body)
        return store.repo_enums.model_dump()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @app.post("/export/jsx", tags=["export"])
    def export_jsx_endpoint(body: ExportRequest):
        content = export_jsx(store, body.product, body.variant)
        return Response(content=content, media_type="text/plain",
                        headers={"Content-Disposition": "attachment; filename=requirements.jsx"})

    @app.post("/export/markdown", tags=["export"])
    def export_markdown_endpoint(body: ExportMarkdownRequest):
        content = export_markdown_zip(store, product_id=body.product,
                                       variant=body.variant, split_by=body.split_by)
        return Response(content=content, media_type="application/zip",
                        headers={"Content-Disposition": "attachment; filename=requirements.zip"})

    @app.post("/export/csv", tags=["export"])
    def export_csv_endpoint(body: ExportCSVRequest):
        content = export_csv(store, product_id=body.product,
                              variant=body.variant, fields=body.fields)
        return Response(content=content.encode("utf-8"), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=requirements.csv"})

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @app.get("/validate")
    def run_validation():
        return validate_all(store)

    @app.get("/validate/{uid}")
    def validate_artefact(uid: str):
        return validate_single(store, uid)

    # ------------------------------------------------------------------
    # Git
    # ------------------------------------------------------------------

    @app.get("/git/status")
    def get_git_status():
        return git_status(repo_root)

    @app.post("/git/commit")
    def batch_commit(body: CommitRequest):
        if has_conflicts(repo_root):
            raise _conflict("Working tree has unresolved merge conflicts")
        try:
            # Stage files for listed UIDs
            for uid in body.uids:
                for get_path in (store.req_path, store.principle_path, store.tbd_path):
                    p = get_path(uid)
                    if p.exists():
                        stage_file(repo_root, p)
                        break
            sha = git_commit(repo_root, body.message,
                             store.config.git.commit_name, store.config.git.commit_email)
            return {"commit_sha": sha}
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})

    @app.get("/git/log/{uid}")
    def get_git_log(uid: str):
        for get_path in (store.req_path, store.principle_path, store.tbd_path):
            p = get_path(uid)
            if p.exists():
                return git_log(repo_root, p)
        raise _not_found(uid)

    # ------------------------------------------------------------------
    # CSV Import
    # ------------------------------------------------------------------

    @app.post("/import/csv", status_code=201, tags=["import"])
    async def import_csv(file: bytes = None, body: dict[str, Any] = None):
        """Import requirements from CSV. Accepts raw CSV as request body (text/csv)
        or a JSON body with a 'csv' string field."""
        raise HTTPException(status_code=501, detail={"error": "use_multipart",
            "message": "POST CSV as multipart/form-data file field 'file'"})

    @app.post("/import/csv/upload", status_code=201, tags=["import"])
    async def import_csv_upload(request: "Request"):
        """Import requirements from a CSV file upload or raw CSV body.

        Column mapping (case-insensitive, all optional except 'title'):
          id, title, parentId (or parent_id), status, priority, req_type (or type),
          domain, owner, discipline, component, content.description (or description),
          content.rationale (or rationale), tags (semicolon-separated),
          allocated_to (semicolon-separated), verification_method, safety_related
        """
        import csv, io
        content_type = request.headers.get("content-type", "")
        raw = await request.body()
        try:
            text = raw.decode("utf-8-sig")  # handle BOM
        except Exception:
            text = raw.decode("latin-1")

        reader = csv.DictReader(io.StringIO(text))

        # Normalise column names
        def _norm(name: str) -> str:
            return name.strip().lower().replace(" ", "_").replace(".", "_")

        created = []
        errors = []
        id_to_uid: dict[str, str] = {}

        rows = list(reader)
        # First pass: create all requirements (parentId resolved in second pass)
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
                    "safety_related": normed.get("safety_related", "").lower() in ("true","1","yes"),
                    "content": {
                        "description": normed.get("content_description") or normed.get("description", ""),
                        "rationale":   normed.get("content_rationale") or normed.get("rationale", ""),
                        "extended_description": normed.get("extended_description", ""),
                    },
                    "tags": [t.strip() for t in normed.get("tags","").split(";") if t.strip()],
                    "allocated_to": [t.strip() for t in normed.get("allocated_to","").split(";") if t.strip()],
                }
                if not fields["title"]:
                    errors.append({"row": i+1, "error": "title is required"})
                    continue
                # Defer parentId to second pass
                fields.pop("parentId", None)
                req = store.create_requirement(fields)
                id_to_uid[fields["id"]] = req["uid"]
                created.append(req["uid"])
            except Exception as exc:
                errors.append({"row": i+1, "id": normed.get("id","?"), "error": str(exc)})

        # Second pass: wire up parentId
        for i, row in enumerate(rows):
            normed = {_norm(k): v.strip() for k, v in row.items() if v and v.strip()}
            req_id = normed.get("id", f"IMP-{i+1:04d}")
            parent_ref = normed.get("parentid") or normed.get("parent_id") or normed.get("parentid", "")
            if parent_ref and req_id in id_to_uid:
                parent_uid = id_to_uid.get(parent_ref)
                if parent_uid:
                    store.update_requirement(id_to_uid[req_id], {"parentId": parent_uid}, summary="Import: set parent")

        return {"imported": len(created), "errors": errors, "uids": created}

    # ------------------------------------------------------------------
    # Baselines (git tags)
    # ------------------------------------------------------------------

    @app.get("/baselines", tags=["baselines"])
    def list_baselines():
        """List all baseline tags (prefix: baseline/)."""
        from .git_ops import git_list_tags
        return git_list_tags(repo_root, prefix="baseline/")

    @app.post("/baselines", status_code=201, tags=["baselines"])
    def create_baseline(body: dict[str, Any]):
        """Create a baseline by tagging the current HEAD.
        Body: {name: str, message: str}
        Tag created as baseline/<name>.
        """
        from .git_ops import git_create_tag, ensure_git_config
        name = body.get("name", "").strip().replace(" ", "-")
        if not name:
            raise HTTPException(status_code=422, detail={"error": "validation", "message": "name is required"})
        tag = f"baseline/{name}"
        message = body.get("message", f"Baseline: {name}")
        ensure_git_config(repo_root, store.config.git.commit_name, store.config.git.commit_email)
        try:
            sha = git_create_tag(repo_root, tag, message)
            return {"tag": tag, "sha": sha, "name": name, "message": message}
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})

    @app.get("/baselines/{name}/diff", tags=["baselines"])
    def baseline_diff(name: str):
        """Compare current requirements against a baseline.
        Returns added, removed, and changed requirement IDs.
        """
        from .git_ops import git_diff_tree, git_show_file
        from .fileio import load_yaml as _load_yaml
        tag = f"baseline/{name}"

        changes = git_diff_tree(repo_root, tag)
        req_changes = [c for c in changes if c["path"].startswith("requirements/") and c["path"].endswith(".yaml")]

        result = {"baseline": tag, "added": [], "removed": [], "changed": []}
        for change in req_changes:
            status = change["status"]
            path = repo_root / change["path"]
            if status == "A":
                current = None
                try:
                    current = _load_yaml(path)
                except Exception:
                    pass
                result["added"].append({"id": current.get("id","?") if current else "?", "path": change["path"]})
            elif status == "D":
                old_content = git_show_file(repo_root, tag, repo_root / change["path"])
                if old_content:
                    try:
                        import ruamel.yaml as ry
                        yml = ry.YAML(); old = yml.load(old_content)
                        result["removed"].append({"id": old.get("id","?") if old else "?", "path": change["path"]})
                    except Exception:
                        result["removed"].append({"path": change["path"]})
            elif status in ("M", "R"):
                current = None
                try:
                    current = _load_yaml(path)
                except Exception:
                    pass
                result["changed"].append({
                    "id": current.get("id","?") if current else "?",
                    "path": change["path"],
                    "current_version": current.get("version","?") if current else "?",
                })
        return result

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    @app.get("/metrics", tags=["metrics"])
    def get_metrics():
        """Repository health metrics: counts, status breakdown, coverage gaps, velocity."""
        from collections import Counter
        reqs = [r for r in store.requirements.values() if not r.get("deleted")]
        principles = [p for p in store.principles.values() if not p.get("deleted")]
        tbds = [t for t in store.tbds.values() if not t.get("deleted")]

        status_counts = Counter(r.get("status","draft") for r in reqs)
        domain_counts = Counter(r.get("domain") or "unclassified" for r in reqs)
        priority_counts = Counter(r.get("priority","medium") for r in reqs)

        no_owner = sum(1 for r in reqs if not r.get("owner"))
        no_ac = sum(1 for r in reqs if not r.get("acceptance_criteria"))
        no_rationale = sum(1 for r in reqs if not r.get("content",{}).get("rationale"))
        no_verification = sum(1 for r in reqs if r.get("verification",{}).get("status","not_started") == "not_started")
        safety_related = sum(1 for r in reqs if r.get("safety_related"))
        open_tbds = sum(1 for t in tbds if t.get("status") in ("open","in_progress"))

        # Approval funnel
        approved = status_counts.get("approved", 0)
        in_review = status_counts.get("in_review", 0) + status_counts.get("reviewed", 0)
        draft = status_counts.get("draft", 0)

        # History-based velocity: count commits in last 30 days (approximate from history entries)
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        recent_changes = 0
        for r in reqs:
            for h in r.get("history", []):
                try:
                    dt_str = h.get("date","")
                    if dt_str:
                        dt = datetime.fromisoformat(str(dt_str).replace("Z","+00:00"))
                        if dt > cutoff:
                            recent_changes += 1
                except Exception:
                    pass

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
                "no_owner":       no_owner,
                "no_ac":          no_ac,
                "no_rationale":   no_rationale,
                "not_verified":   no_verification,
            },
            "velocity": {
                "changes_last_30d": recent_changes,
            },
        }

    # ------------------------------------------------------------------
    # Workflow config
    # ------------------------------------------------------------------

    @app.get("/workflow", tags=["workflow"])
    def get_workflow():
        """Return the configured workflow states and transitions."""
        return store.config.workflow.model_dump()

    @app.put("/workflow", tags=["workflow"])
    def update_workflow(body: dict[str, Any]):
        """Update workflow configuration. Writes to .reqtool/config.yaml."""
        from .fileio import load_yaml, save_yaml
        from .models import WorkflowConfig
        config_path = repo_root / ".reqtool" / "config.yaml"
        config_data = load_yaml(config_path) if config_path.exists() else {}
        config_data["workflow"] = body
        save_yaml(config_path, config_data)
        store.config.workflow = WorkflowConfig.model_validate(body)
        return store.config.workflow.model_dump()

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    @app.get("/templates", tags=["templates"])
    def list_templates():
        """Return available requirement templates (from .reqtool/templates.yaml or defaults)."""
        from .fileio import load_yaml as _load_yaml
        # Project-level templates override defaults
        project_path = repo_root / ".reqtool" / "templates.yaml"
        default_path = Path(__file__).parent / "defaults" / "templates.yaml"
        for path in (project_path, default_path):
            if path.exists():
                data = _load_yaml(path)
                if isinstance(data, list):
                    return data
        return []

    @app.put("/templates", tags=["templates"])
    def save_templates(body: list[dict[str, Any]]):
        """Save templates to .reqtool/templates.yaml in the project."""
        from .fileio import save_yaml
        save_yaml(repo_root / ".reqtool" / "templates.yaml", body)
        return {"saved": len(body)}

    # ------------------------------------------------------------------
    # Generic artefact attachments (requirements, principles, TBDs)
    # ------------------------------------------------------------------

    @app.get("/artefacts/{uid}/attachments", tags=["attachments"])
    def list_artefact_attachments(uid: str):
        return store.list_attachments(uid)

    @app.post("/artefacts/{uid}/attachments", status_code=201, tags=["attachments"])
    async def upload_artefact_attachment(uid: str, request: Request, author: str = "reqtool"):
        import re as _re
        data = await request.body()
        if not data:
            raise HTTPException(status_code=422, detail={"error": "empty", "message": "No file data"})
        if store._get_artefact(uid) is None:
            raise _not_found(uid)
        content_disposition = request.headers.get("content-disposition", "")
        filename = "attachment"
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=")[-1].strip('"').strip()
        description = request.headers.get("x-description", "")
        filename = _re.sub(r'[^\w\-_\. ]', '_', filename)[:200]
        record = store.add_attachment(uid, filename, data, author=author, description=description)
        _fire_webhook(store, "attachment_added", {"uid": uid, "filename": filename})
        return record

    @app.get("/artefacts/{uid}/attachments/{filename}", tags=["attachments"])
    def download_artefact_attachment(uid: str, filename: str):
        path = store.attachment_dir(uid) / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
        import mimetypes
        mime, _ = mimetypes.guess_type(filename)
        return Response(content=path.read_bytes(), media_type=mime or "application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.delete("/artefacts/{uid}/attachments/{filename}", tags=["attachments"])
    def delete_artefact_attachment(uid: str, filename: str):
        ok = store.delete_attachment(uid, filename)
        if not ok:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
        return {"deleted": filename}

    # ------------------------------------------------------------------
    # Generic artefact comments (requirements, principles, TBDs)
    # ------------------------------------------------------------------

    @app.get("/artefacts/{uid}/comments", tags=["comments"])
    def list_artefact_comments(uid: str):
        return store.get_comments(uid)

    @app.post("/artefacts/{uid}/comments", status_code=201, tags=["comments"])
    def add_artefact_comment(uid: str, body: dict[str, Any]):
        if store._get_artefact(uid) is None:
            raise _not_found(uid)
        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=422, detail={"error": "validation", "message": "text is required"})
        author = body.get("author", "anonymous")
        reply_to = body.get("reply_to")
        comment = store.add_comment(uid, text, author, reply_to=reply_to)
        _fire_webhook(store, "comment_added", {"uid": uid, "comment_uid": comment["uid"], "author": author})
        return comment

    @app.put("/artefacts/{uid}/comments/{comment_uid}", tags=["comments"])
    def update_artefact_comment(uid: str, comment_uid: str, body: dict[str, Any]):
        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=422, detail={"error": "validation", "message": "text is required"})
        result = store.update_comment(uid, comment_uid, text)
        if result is None:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
        return result

    @app.post("/artefacts/{uid}/comments/{comment_uid}/resolve", tags=["comments"])
    def resolve_artefact_comment(uid: str, comment_uid: str, body: dict[str, Any] = None):
        resolved = (body or {}).get("resolved", True)
        result = store.resolve_comment(uid, comment_uid, resolved)
        if result is None:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
        return result

    @app.delete("/artefacts/{uid}/comments/{comment_uid}", tags=["comments"])
    def delete_artefact_comment(uid: str, comment_uid: str):
        ok = store.delete_comment(uid, comment_uid)
        if not ok:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
        return {"deleted": comment_uid}

    # ------------------------------------------------------------------
    # Attachments (requirement-scoped -- kept for backwards compatibility)
    # ------------------------------------------------------------------

    @app.get("/requirements/{uid}/attachments", tags=["attachments"])
    def list_attachments(uid: str):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        return req.get("attachments", [])

    @app.post("/requirements/{uid}/attachments", status_code=201, tags=["attachments"])
    async def upload_attachment(uid: str, request: Request, author: str = "reqtool"):
        """Upload a file and attach it to a requirement.
        Send raw file bytes with Content-Disposition: attachment; filename=<name>
        """
        import re as _re
        # Read body first (async yield happens here, before any write)
        data = await request.body()
        if not data:
            raise HTTPException(status_code=422, detail={"error": "empty", "message": "No file data received"})

        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        content_disposition = request.headers.get("content-disposition", "")
        filename = "attachment"
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=")[-1].strip('"').strip()
        description = request.headers.get("x-description", "")
        filename = _re.sub(r'[^\w\-_\. ]', '_', filename)[:200]

        # All synchronous writes happen together after the await
        record = store.add_attachment(uid, filename, data, author=author, description=description)
        _fire_webhook(store, "attachment_added", {"uid": uid, "filename": filename})
        return record

    @app.get("/requirements/{uid}/attachments/{filename}", tags=["attachments"])
    def download_attachment(uid: str, filename: str):
        path = store.attachment_dir(uid) / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
        import mimetypes
        mime, _ = mimetypes.guess_type(filename)
        mime = mime or "application/octet-stream"
        return Response(
            content=path.read_bytes(),
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.delete("/requirements/{uid}/attachments/{filename}", tags=["attachments"])
    def delete_attachment(uid: str, filename: str):
        ok = store.delete_attachment(uid, filename)
        if not ok:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Attachment '{filename}' not found"})
        return {"deleted": filename}

    # ------------------------------------------------------------------
    # Comments / Discussion
    # ------------------------------------------------------------------

    @app.get("/requirements/{uid}/comments", tags=["comments"])
    def get_comments(uid: str):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        return store.get_comments(uid)

    @app.post("/requirements/{uid}/comments", status_code=201, tags=["comments"])
    def add_comment(uid: str, body: dict[str, Any]):
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=422, detail={"error": "validation", "message": "text is required"})
        author = body.get("author", "anonymous")
        reply_to = body.get("reply_to")
        comment = store.add_comment(uid, text, author, reply_to=reply_to)
        _fire_webhook(store, "comment_added", {"uid": uid, "comment_uid": comment["uid"], "author": author})
        return comment

    @app.put("/requirements/{uid}/comments/{comment_uid}", tags=["comments"])
    def update_comment(uid: str, comment_uid: str, body: dict[str, Any]):
        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=422, detail={"error": "validation", "message": "text is required"})
        result = store.update_comment(uid, comment_uid, text)
        if result is None:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
        return result

    @app.post("/requirements/{uid}/comments/{comment_uid}/resolve", tags=["comments"])
    def resolve_comment(uid: str, comment_uid: str, body: dict[str, Any] = None):
        resolved = (body or {}).get("resolved", True)
        result = store.resolve_comment(uid, comment_uid, resolved)
        if result is None:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
        return result

    @app.delete("/requirements/{uid}/comments/{comment_uid}", tags=["comments"])
    def delete_comment(uid: str, comment_uid: str):
        ok = store.delete_comment(uid, comment_uid)
        if not ok:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Comment not found"})
        return {"deleted": comment_uid}

    # ------------------------------------------------------------------
    # Custom field schema
    # ------------------------------------------------------------------

    @app.get("/custom-fields", tags=["custom-fields"])
    def get_custom_field_schema():
        return store.load_custom_field_schema()

    @app.put("/custom-fields", tags=["custom-fields"])
    def update_custom_field_schema(body: list[dict[str, Any]]):
        store.save_custom_field_schema(body)
        return {"saved": len(body)}

    # ------------------------------------------------------------------
    # Webhooks config
    # ------------------------------------------------------------------

    @app.get("/webhooks", tags=["webhooks"])
    def list_webhooks():
        return [w.model_dump() for w in store.config.webhooks]

    @app.post("/webhooks", status_code=201, tags=["webhooks"])
    def add_webhook(body: dict[str, Any]):
        from .fileio import load_yaml, save_yaml
        from .models import WebhookConfig
        wh = WebhookConfig.model_validate(body)
        store.config.webhooks.append(wh)
        config_path = repo_root / ".reqtool" / "config.yaml"
        config_data = load_yaml(config_path) if config_path.exists() else {}
        config_data["webhooks"] = [w.model_dump() for w in store.config.webhooks]
        save_yaml(config_path, config_data)
        return wh.model_dump()

    @app.delete("/webhooks/{idx}", tags=["webhooks"])
    def delete_webhook(idx: int):
        if idx < 0 or idx >= len(store.config.webhooks):
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Webhook {idx} not found"})
        from .fileio import load_yaml, save_yaml
        store.config.webhooks.pop(idx)
        config_path = repo_root / ".reqtool" / "config.yaml"
        config_data = load_yaml(config_path) if config_path.exists() else {}
        config_data["webhooks"] = [w.model_dump() for w in store.config.webhooks]
        save_yaml(config_path, config_data)
        return {"deleted": idx}

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    @app.get("/diff", tags=["diff"])
    def get_diff(since: str = "", path: str = ""):
        """Human-readable diff of requirement changes since a ref or last commit."""
        from .git_ops import _run_git
        ref = since or "HEAD~1"
        rc, out, err = _run_git(["diff", "--name-only", ref, "HEAD", "--", "requirements/", "principles/", "tbds/"], repo_root)
        if rc != 0 or not out:
            return {"ref": ref, "changes": []}

        changes = []
        for rel_path in out.splitlines():
            full = repo_root / rel_path
            # Get old version
            rc2, old_content, _ = _run_git(["show", f"{ref}:{rel_path}"], repo_root)
            # Get new version
            if full.exists():
                from .fileio import load_yaml
                new_data = load_yaml(full)
            else:
                new_data = None

            old_data = None
            if rc2 == 0 and old_content:
                import ruamel.yaml as ry
                yml = ry.YAML()
                try:
                    old_data = yml.load(old_content)
                except Exception:
                    pass

            if new_data is None and old_data is not None:
                changes.append({"action": "deleted", "id": old_data.get("id","?"), "path": rel_path})
                continue
            if old_data is None and new_data is not None:
                changes.append({"action": "added", "id": new_data.get("id","?"), "title": new_data.get("title",""), "path": rel_path})
                continue
            if old_data and new_data:
                # Find changed fields
                COMPARE_FIELDS = ["title","status","priority","req_type","domain","owner",
                                   "content","acceptance_criteria","relationships","allocated_to"]
                diffs = {}
                for field in COMPARE_FIELDS:
                    old_val = old_data.get(field)
                    new_val = new_data.get(field)
                    if old_val != new_val:
                        if field == "content":
                            for sub in ("description","rationale"):
                                if isinstance(old_val,dict) and isinstance(new_val,dict):
                                    if old_val.get(sub) != new_val.get(sub):
                                        diffs[f"content.{sub}"] = {"from": str(old_val.get(sub,""))[:120], "to": str(new_val.get(sub,""))[:120]}
                        else:
                            diffs[field] = {"from": str(old_val)[:120], "to": str(new_val)[:120]}
                if diffs:
                    changes.append({
                        "action": "changed",
                        "id": new_data.get("id","?"),
                        "version_from": old_data.get("version","?"),
                        "version_to":   new_data.get("version","?"),
                        "changes": diffs,
                        "path": rel_path,
                    })
        return {"ref": ref, "total": len(changes), "changes": changes}

    # ------------------------------------------------------------------
    # Markdown render
    # ------------------------------------------------------------------

    @app.post("/render/markdown", tags=["meta"])
    def render_markdown(body: dict[str, Any]):
        """Render Markdown text to safe HTML."""
        text = body.get("text", "")
        try:
            import markdown as md
            html = md.markdown(text, extensions=["tables","fenced_code","nl2br"])
        except ImportError:
            import html as _html
            html = _html.escape(text).replace("\n","<br/>")
        return {"html": html}

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/health", tags=["meta"])
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "repo_id": store.config.repo_id,
            "requirements": len([r for r in store.requirements.values() if not r.get("deleted")]),
            "principles": len([p for p in store.principles.values() if not p.get("deleted")]),
            "tbds": len([t for t in store.tbds.values() if not t.get("deleted")]),
        }

    # ------------------------------------------------------------------
    # Impact analysis
    # ------------------------------------------------------------------

    @app.get("/requirements/{uid}/impact", tags=["requirements"])
    def requirement_impact(uid: str):
        """
        Return the transitive downstream impact closure for a requirement.
        Downstream items are those linked via derived_from, depends_on, implements, or satisfies.
        """
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        return store.compute_impact(uid)

    # ------------------------------------------------------------------
    # Hierarchy / type config
    # ------------------------------------------------------------------

    @app.get("/hierarchy", tags=["hierarchy"])
    def get_hierarchy():
        """Return the full hierarchy configuration (types, workflows, rules)."""
        return {
            "types": {k: v.model_dump() for k, v in store.hierarchy.types.items()},
            "hierarchy": {k: v.model_dump() for k, v in store.hierarchy.hierarchy.items()},
            "workflows": {k: v.model_dump() for k, v in store.hierarchy.workflows.items()},
            "dor": store.hierarchy.dor,
            "dod": store.hierarchy.dod,
            "cross_layer_rules": [r.model_dump() for r in store.hierarchy.cross_layer_rules],
            "default_relationship_types": [r.model_dump() for r in store.hierarchy.default_relationship_types],
        }

    @app.get("/hierarchy/types", tags=["hierarchy"])
    def list_types():
        """Return the configured item types with their metadata."""
        return {k: v.model_dump() for k, v in store.hierarchy.types.items()}

    @app.get("/hierarchy/children/{req_type}", tags=["hierarchy"])
    def allowed_children(req_type: str):
        """Return the allowed child types for a given parent type."""
        return {"req_type": req_type, "allowed_children": store.get_allowed_children(req_type)}

    @app.post("/requirements/{uid}/transition", tags=["requirements"])
    def transition_requirement(uid: str, body: dict):
        """
        Transition a requirement to a new status with workflow guard enforcement.
        Body: {to_state: str}
        Returns 409 if the transition is blocked by a guard.
        """
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        to_state = body.get("to_state", "")
        if not to_state:
            raise HTTPException(status_code=422, detail={"error": "validation", "message": "to_state is required"})
        error = store.validate_transition(req, to_state)
        if error:
            raise HTTPException(status_code=409, detail={"error": "workflow_guard", "message": error})
        old_status = req.get("status")
        result = store.update_requirement(uid, {"status": to_state}, summary=f"Transitioned to {to_state}")
        _fire_webhook(store, "status_changed", {
            "uid": uid, "id": req.get("id"), "from": old_status, "to": to_state,
        })
        _broadcast_sync("status_changed", {"uid": uid, "id": req.get("id"), "from": old_status, "to": to_state})
        return result

    # ------------------------------------------------------------------
    # Estimate rollup
    # ------------------------------------------------------------------

    @app.get("/requirements/{uid}/rollup", tags=["requirements"])
    def estimate_rollup(uid: str):
        """Return the rolled-up estimate sum for all direct children."""
        req = store.get_requirement(uid)
        if req is None:
            raise _not_found(uid)
        rollup = store.compute_estimate_rollup(uid)
        return {"uid": uid, "estimate_rollup": rollup, "estimate_unit": store.repo_enums.estimate_unit}

    # ------------------------------------------------------------------
    # Kanban
    # ------------------------------------------------------------------

    @app.get("/kanban", tags=["kanban"])
    def get_kanban(
        req_type: Optional[str] = None,
        iteration: Optional[str] = None,
        owner: Optional[str] = None,
        assignee: Optional[str] = None,
    ):
        """
        Column-per-state kanban board.
        Filter by req_type, iteration, owner, or assignee.
        """
        return store.build_kanban(
            req_type=req_type,
            iteration=iteration,
            owner=owner,
            assignee=assignee,
        )

    # ------------------------------------------------------------------
    # Filter presets
    # ------------------------------------------------------------------

    @app.get("/filter-presets", tags=["filter-presets"])
    def list_filter_presets():
        return store.list_filter_presets()

    @app.put("/filter-presets/{preset_id}", tags=["filter-presets"])
    def save_filter_preset(preset_id: str, body: dict):
        body["id"] = preset_id
        if not body.get("label"):
            raise HTTPException(status_code=422, detail={"error": "validation", "message": "label is required"})
        return store.save_filter_preset(body)

    @app.delete("/filter-presets/{preset_id}", tags=["filter-presets"])
    def delete_filter_preset(preset_id: str):
        ok = store.delete_filter_preset(preset_id)
        if not ok:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Preset '{preset_id}' not found"})
        return {"deleted": preset_id}

    # ------------------------------------------------------------------
    # Help system
    # ------------------------------------------------------------------

    @app.get("/help", tags=["meta"])
    def get_help(topic: Optional[str] = None):
        """Return help content from help.yaml. Pass ?topic=<key> for a specific section."""
        from .fileio import load_yaml as _load_yaml
        project_path = repo_root / ".reqtool" / "help.yaml"
        default_path = Path(__file__).parent / "defaults" / "help.yaml"
        for path in (project_path, default_path):
            if path.exists():
                data = _load_yaml(path)
                if topic:
                    return data.get(topic, {})
                return data
        return {}

    # ------------------------------------------------------------------
    # CI badge
    # ------------------------------------------------------------------

    @app.get("/badge/validated", tags=["meta"])
    def validation_badge():
        """Return a Shields.io-compatible SVG badge for CI integration."""
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

    # ------------------------------------------------------------------
    # Static UI (or fallback landing page when dist is not built)
    # ------------------------------------------------------------------
    ui_dist = Path(__file__).parent / "ui" / "dist"
    if ui_dist.exists():
        app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="ui")
    else:
        @app.get("/", include_in_schema=False)
        def landing():
            """Fallback landing page served when the React UI has not been built."""
            from fastapi.responses import HTMLResponse
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>reqtool {__version__}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0d1117; color: #e6edf3; min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
    }}
    .card {{
      background: #161b22; border: 1px solid #30363d; border-radius: 12px;
      padding: 40px 48px; max-width: 560px; width: 100%; text-align: center;
    }}
    h1 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 8px; }}
    .version {{ color: #8b949e; font-size: 0.9rem; margin-bottom: 32px; }}
    .status {{
      background: #1c2128; border: 1px solid #30363d; border-radius: 8px;
      padding: 16px 20px; margin-bottom: 32px; text-align: left;
    }}
    .status-row {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.9rem; }}
    .ok {{ color: #3fb950; font-weight: 600; }}
    .links {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }}
    a {{
      display: inline-block; padding: 10px 20px; border-radius: 6px;
      text-decoration: none; font-size: 0.9rem; font-weight: 500;
    }}
    .btn-primary {{ background: #238636; color: #fff; border: 1px solid #2ea043; }}
    .btn-primary:hover {{ background: #2ea043; }}
    .btn-secondary {{ background: #21262d; color: #e6edf3; border: 1px solid #30363d; }}
    .btn-secondary:hover {{ background: #30363d; }}
    .note {{
      margin-top: 28px; padding: 14px 16px;
      background: #161b22; border: 1px solid #30363d; border-radius: 6px;
      font-size: 0.8rem; color: #8b949e; text-align: left; line-height: 1.6;
    }}
    code {{
      background: #0d1117; border: 1px solid #30363d; border-radius: 4px;
      padding: 1px 6px; font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.85em;
      color: #79c0ff;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>reqtool</h1>
    <p class="version">v{__version__} &mdash; API server running</p>

    <div class="status">
      <div class="status-row"><span>API server</span><span class="ok">&#10003; running</span></div>
      <div class="status-row"><span>Repository</span><span style="color:#8b949e">{store.config.repo_title or store.config.repo_id or "unnamed"}</span></div>
      <div class="status-row"><span>Requirements</span><span style="color:#e6edf3">{len([r for r in store.requirements.values() if not r.get("deleted")])}</span></div>
      <div class="status-row"><span>React UI</span><span style="color:#e3b341">&#9888; not built</span></div>
    </div>

    <div class="links">
      <a href="/docs" class="btn-primary">API Docs (Swagger)</a>
      <a href="/redoc" class="btn-secondary">ReDoc</a>
      <a href="/health" class="btn-secondary">Health</a>
      <a href="/openapi.json" class="btn-secondary">OpenAPI JSON</a>
    </div>

    <div class="note">
      <strong>To build the React UI:</strong><br>
      <code>cd src/reqtool/ui</code><br>
      <code>npm install &amp;&amp; npm run build</code><br><br>
      The API is fully functional without the UI &mdash; use the Swagger docs above
      or any HTTP client.
    </div>
  </div>
</body>
</html>"""
            return HTMLResponse(content=html)

    return app
