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
from reqtool.fileio import save_yaml, uuid7, utcnow_iso
from .deps import get_store, not_found

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/modules", tags=["modules"])
def list_modules(store: Store = Depends(get_store)):
    return list(store.modules.values())


@router.get("/modules/{module_id}", tags=["modules"])
def get_module(module_id: str, store: Store = Depends(get_store)):
    m = store.modules.get(module_id)
    if m is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Module '{module_id}' not found"})
    return {
        "manifest": m,
        "requirements": list(store.module_requirements.get(module_id, {}).values()),
    }


@router.post("/modules/{module_id}/import", tags=["modules"])
def import_module(module_id: str, product_id: str = "", store: Store = Depends(get_store)):
    if not product_id:
        results = []
        for pid, product in store.products.items():
            if any(m.get("id") == module_id for m in product.get("modules", [])):
                lock = store.import_module(pid, module_id)
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


@router.post("/modules/{module_id}/fetch-remote", tags=["modules"])
def fetch_remote_module(module_id: str, store: Store = Depends(get_store)):
    try:
        return store.fetch_remote_module(module_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "git_error", "message": str(e)})


@router.get("/modules/{module_id}/verify", tags=["modules"])
def verify_module(module_id: str, product_id: str = "", store: Store = Depends(get_store)):
    if not product_id:
        for pid, product in store.products.items():
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
    return list(store.products.values())


@router.post("/products", status_code=201, tags=["products"])
def create_product(body: dict[str, Any], store: Store = Depends(get_store)):
    """Create a new product manifest."""
    product_id = body.get("id", "").strip()
    if not product_id:
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "id is required"})
    if product_id in store.products:
        raise HTTPException(status_code=409, detail={"error": "conflict", "message": f"Product '{product_id}' already exists"})
    prod_dir = store.root / "products" / product_id
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


@router.get("/products/{product_id}", tags=["products"])
def get_product(product_id: str, store: Store = Depends(get_store)):
    p = store.products.get(product_id)
    if p is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Product '{product_id}' not found"})
    return p


@router.get("/products/{product_id}/tree", tags=["products"])
def product_tree(product_id: str, variant: Optional[str] = None, store: Store = Depends(get_store)):
    return store.build_tree(product_id, variant)


@router.get("/products/{product_id}/matrix", tags=["products"])
def product_matrix(product_id: str, store: Store = Depends(get_store)):
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
