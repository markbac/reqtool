"""
reqtool.routers.modules
=======================
FastAPI router for module and product management.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException

from reqtool.store import Store
from reqtool import __version__
from reqtool.fileio import save_yaml, uuid7, utcnow_iso, validate_id, compute_product_hash
from reqtool.features import registry
from .deps import get_store

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/modules", tags=["modules"])
def list_modules(store: Store = Depends(get_store)):
    return list(store.module_map().values())


def _module_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except registry.ModuleError as exc:
        raise HTTPException(status_code=409, detail={"error": "conflict", "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "validation", "message": str(exc)})


@router.post("/modules", status_code=201, tags=["modules"])
def create_module(body: dict[str, Any], store: Store = Depends(get_store)):
    return _module_call(registry.create_module, store, str(body.get("id", "")).strip(),
                        str(body.get("title", "")), str(body.get("description", "")))


@router.post("/modules/{module_id}/version", tags=["modules"])
def bump_module_version(module_id: str, body: dict[str, Any], store: Store = Depends(get_store)):
    increment = body.get("increment", "patch")
    if increment not in ("major", "minor", "patch"):
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "increment must be major, minor or patch"})
    return _module_call(registry.bump_module, store, module_id, increment, str(body.get("note", "")))


@router.post("/modules/{module_id}/clone", status_code=201, tags=["modules"])
def clone_module(module_id: str, body: dict[str, Any], store: Store = Depends(get_store)):
    return _module_call(registry.clone_module, store, module_id, str(body.get("id", "")).strip())


@router.get("/modules/{module_id}/consumers", tags=["modules"])
def module_consumers(module_id: str, store: Store = Depends(get_store)):
    if module_id not in store.module_map():
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Module '{module_id}' not found"})
    return registry.consumers(store, module_id)


@router.post("/modules/{module_id}/pin", tags=["modules"])
def pin_module(module_id: str, body: dict[str, Any], store: Store = Depends(get_store)):
    """Pin a remote module to a tag, branch or commit; the next fetch records the exact commit."""
    return _module_call(registry.pin, store, module_id, str(body.get("ref", "")).strip())


@router.get("/modules/{module_id}/update-preview", tags=["modules"])
def module_update_preview(module_id: str, ref: str, store: Store = Depends(get_store)):
    """Files a new ref would add, remove or change, with the products that consume the module."""
    return _module_call(registry.update_preview, store, module_id, ref)


@router.get("/modules/{module_id}", tags=["modules"])
def get_module(module_id: str, store: Store = Depends(get_store)):
    m = store.module_map().get(module_id)
    if m is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Module '{module_id}' not found"})
    return {
        "manifest": m,
        "requirements": list(store.module_requirement_map().get(module_id, {}).values()),
    }


@router.post("/modules/{module_id}/import", tags=["modules"])
def import_module(module_id: str, product_id: str = "", store: Store = Depends(get_store)):
    if not product_id:
        results = []
        for pid, product in store.product_map().items():
            if any(m.get("id") == module_id for m in product.get("modules", [])):
                try:
                    lock = store.import_module(pid, module_id)
                except ValueError as e:
                    raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})
                results.append({"product": pid, "locked": len(lock.get("locked", []))})
        if not results:
            raise HTTPException(status_code=404, detail={
                "error": "not_found",
                "message": f"Module '{module_id}' not referenced by any product",
            })
        return {"status": "ok", "results": results}
    try:
        lock = store.import_module(product_id, module_id)
        return {"status": "ok", "product": product_id, "module": module_id,
                "locked_entries": len(lock.get("locked", []))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})


@router.post("/products/{product_id}/modules", status_code=201, tags=["products"])
def include_module(product_id: str, body: dict[str, Any], store: Store = Depends(get_store)):
    """Make a product include a module and lock the version it now has."""
    module_id = str(body.get("module_id", "")).strip()
    if not module_id:
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "module_id is required"})
    try:
        lock = store.include_module(product_id, module_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})
    return {"status": "ok", "product": product_id, "module": module_id, "locked_entries": len(lock.get("locked", []))}


@router.post("/modules/{module_id}/fetch-remote", tags=["modules"])
def fetch_remote_module(module_id: str, store: Store = Depends(get_store)):
    try:
        return store.fetch_remote_module(module_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "git_error", "message": str(e)})


@router.get("/modules/{module_id}/verify", tags=["modules"])
def verify_module(module_id: str, product_id: str = "", store: Store = Depends(get_store)):
    if not product_id:
        for pid, product in store.product_map().items():
            if any(m.get("id") == module_id for m in product.get("modules", [])):
                product_id = pid
                break
    if not product_id:
        raise HTTPException(status_code=404, detail={
            "error": "not_found",
            "message": f"Module '{module_id}' not referenced by any product",
        })
    return store.verify_module(product_id, module_id)


@router.get("/products", tags=["products"])
def list_products(store: Store = Depends(get_store)):
    return list(store.product_map().values())


@router.post("/products", status_code=201, tags=["products"])
def create_product(body: dict[str, Any], store: Store = Depends(get_store)):
    """Create a new product manifest."""
    product_id = str(body.get("id", "")).strip()
    if not product_id:
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "id is required"})
    validate_id(product_id, "product id")
    if product_id in store.product_map():
        raise HTTPException(status_code=409, detail={"error": "conflict", "message": f"Product '{product_id}' already exists"})
    prod_dir = store.root / "products" / product_id
    if not prod_dir.resolve().is_relative_to((store.root / "products").resolve()):
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "invalid product id"})
    prod_dir.mkdir(parents=True, exist_ok=True)
    now = utcnow_iso()
    product = {
        "schema_version": "1.0.0", "type": "product", "tool_version": __version__,
        "uid": uuid7(), "id": product_id,
        "title": body.get("title", product_id),
        "version": "1.0.0",
        "content": body.get("content", {"description": ""}),
        "modules": [], "root_requirements": [], "display_order": [],
        "content_hash": "", "created": now, "last_modified": now, "history": [],
    }
    product["content_hash"] = compute_product_hash(product)
    save_yaml(prod_dir / "_product.yaml", product)
    store.register_product(product_id, product)
    return product


@router.get("/products/{product_id}", tags=["products"])
def get_product(product_id: str, store: Store = Depends(get_store)):
    p = store.product_map().get(product_id)
    if p is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Product '{product_id}' not found"})
    return p


@router.get("/products/{product_id}/tree", tags=["products"])
def product_tree(product_id: str, variant: Optional[str] = None, store: Store = Depends(get_store)):
    return store.build_tree(product_id, variant)


@router.get("/products/{product_id}/matrix", tags=["products"])
def product_matrix(product_id: str, store: Store = Depends(get_store)):
    """Allocation matrix: requirements x teams."""
    if product_id not in store.product_map():
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Product '{product_id}' not found"})
    in_product: set[str] = set()

    def collect(nodes: list) -> None:
        for n in nodes:
            in_product.add(n["uid"])
            collect(n.get("children", []))
    collect(store.build_tree(product_id))
    known = {**{u: r for mod in store.module_requirement_map().values() for u, r in mod.items()}, **store.requirement_map()}
    reqs = [r for u, r in known.items() if u in in_product and not r.get("deleted")]
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
