"""
reqtool.features.registry
=========================
Module management: create, version, clone, list consumers, pin a remote to a ref and preview an
update before accepting it (ENH-08, FEAT-08).
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any

from reqtool import __version__
from reqtool.fileio import bump_version, load_yaml, save_yaml, utcnow_iso, uuid7, validate_id
from reqtool.store_parts.remote import _git_remote, _validate_remote_ref, _validate_remote_url


class ModuleError(ValueError):
    pass


def _manifest(store, module_id: str) -> Path:
    validate_id(module_id, "module id")
    return store.root / "modules" / module_id / "_module.yaml"


def create_module(store, module_id: str, title: str = "", description: str = "") -> dict[str, Any]:
    path = _manifest(store, module_id)
    if path.exists():
        raise ModuleError(f"Module '{module_id}' already exists")
    now = utcnow_iso()
    data = {"schema_version": "1.0.0", "type": "module", "tool_version": __version__, "uid": uuid7(),
            "id": module_id, "title": title or module_id, "version": "1.0.0",
            "content": {"description": description}, "requirements": [], "requires": [],
            "created": now, "last_modified": now, "history": []}
    with store.lock:
        save_yaml(path, data)
        store.reload_modules()
    return data


def bump_module(store, module_id: str, increment: str = "patch", note: str = "") -> dict[str, Any]:
    path = _manifest(store, module_id)
    if not path.exists():
        raise ModuleError(f"Module '{module_id}' not found")
    with store.lock:
        data = load_yaml(path)
        data["version"] = bump_version(data.get("version", "1.0.0"), increment)
        data["last_modified"] = utcnow_iso()
        data["history"] = list(data.get("history") or []) + [
            {"version": data["version"], "date": data["last_modified"], "summary": note or f"{increment} release"}]
        save_yaml(path, data)
        store.reload_modules()
    return data


def clone_module(store, module_id: str, new_id: str) -> dict[str, Any]:
    src, dest = _manifest(store, module_id), _manifest(store, new_id)
    if not src.exists():
        raise ModuleError(f"Module '{module_id}' not found")
    if dest.exists():
        raise ModuleError(f"Module '{new_id}' already exists")
    with store.lock:
        shutil.copytree(src.parent, dest.parent, ignore=shutil.ignore_patterns("remote", ".git"))
        data = load_yaml(dest)
        now = utcnow_iso()
        data.update({"uid": uuid7(), "id": new_id, "title": f"{data.get('title', module_id)} (copy)",
                     "version": "1.0.0", "created": now, "last_modified": now, "history": []})
        for key in ("git_remote", "git_ref", "pinned_commit"):
            data.pop(key, None)
        save_yaml(dest, data)
        store.reload_modules()
    return data


def consumers(store, module_id: str) -> list[dict[str, Any]]:
    """Products that include the module, with the version each one has locked."""
    out = []
    for pid, product in store.products.items():
        if not any(m.get("id") == module_id for m in product.get("modules") or []):
            continue
        lock = store.root / "products" / pid / "_product.lock"
        locked_version = None
        if lock.exists():
            try:
                for entry in load_yaml(lock).get("locked") or []:
                    if entry.get("module") == module_id or entry.get("id") == module_id:
                        locked_version = entry.get("version")
            except Exception:
                pass
        out.append({"product": pid, "title": product.get("title", pid), "locked_version": locked_version})
    return out


def pin(store, module_id: str, ref: str) -> dict[str, Any]:
    """Pin a remote module to a tag, branch or commit. Takes effect on the next fetch."""
    path = _manifest(store, module_id)
    if not path.exists():
        raise ModuleError(f"Module '{module_id}' not found")
    try:
        _validate_remote_ref(ref)
    except ValueError as exc:
        raise ModuleError(str(exc))
    with store.lock:
        data = load_yaml(path)
        if not data.get("git_remote"):
            raise ModuleError(f"Module '{module_id}' has no git_remote to pin")
        data["git_ref"] = ref
        data["last_modified"] = utcnow_iso()
        save_yaml(path, data)
        store.reload_modules()
    return data


def _clone(remote: str, ref: str, dest: Path) -> None:
    _git_remote(["clone", "--depth", "1", "--branch", ref, "--", remote, str(dest)], dest.parent)


def _digests(folder: Path) -> dict[str, str]:
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*.yaml")) if ".git" not in p.parts}


def update_preview(store, module_id: str, ref: str) -> dict[str, Any]:
    """Compare the fetched copy with what ``ref`` would bring, so an update is reviewed before it is accepted."""
    path = _manifest(store, module_id)
    if not path.exists():
        raise ModuleError(f"Module '{module_id}' not found")
    remote = str(load_yaml(path).get("git_remote", "")).strip()
    if not remote:
        raise ModuleError(f"Module '{module_id}' has no git_remote")
    _validate_remote_url(remote)
    _validate_remote_ref(ref)
    current = _digests(path.parent / "remote") if (path.parent / "remote").is_dir() else {}
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "candidate"
        _clone(remote, ref, dest)
        candidate = _digests(dest)
    return {"module": module_id, "ref": ref,
            "added": sorted(set(candidate) - set(current)),
            "removed": sorted(set(current) - set(candidate)),
            "changed": sorted(k for k in set(current) & set(candidate) if current[k] != candidate[k]),
            "consumers": consumers(store, module_id)}
