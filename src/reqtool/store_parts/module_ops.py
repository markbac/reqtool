"""Importing, verifying and fetching modules for a product."""

from __future__ import annotations

from typing import Any

import logging

from reqtool.fileio import utcnow_iso, validate_id
from reqtool.vcs import _validate_remote_ref, _validate_remote_url
from .locking import _locked


from reqtool.store_parts._host import StoreHost

log = logging.getLogger(__name__)


class ModuleOpsMixin(StoreHost):
    @_locked
    def include_module(self, product_id: str, module_id: str) -> dict[str, Any]:
        """Add ``module_id`` to the product's module list (once) and lock it. Returns the lock."""
        from reqtool.fileio import compute_product_hash
        if product_id not in self.products:
            raise ValueError(f"Product '{product_id}' not found")
        if module_id not in self.modules:
            raise ValueError(f"Module '{module_id}' not found")
        product = self.products[product_id]
        if not any(m.get("id") == module_id for m in product.get("modules") or []):
            product["modules"] = list(product.get("modules") or []) + [{"id": module_id}]
            product["last_modified"] = utcnow_iso()
            product["content_hash"] = compute_product_hash(product)
            self.storage.write(self.root / "products" / validate_id(product_id, "product id") / "_product.yaml", product)
        return self.import_module(product_id, module_id)

    @_locked
    def import_module(
        self,
        product_id: str,
        module_id: str,
        locked_by: str = "reqtool",
    ) -> dict[str, Any]:
        """
        Generate / update the lock entry for a module in a product.
        Writes _product.lock alongside _product.yaml.
        Returns the lock dict.
        """
        import hashlib

        if product_id not in self.products:
            raise ValueError(f"Product '{product_id}' not found")
        if module_id not in self.modules:
            raise ValueError(f"Module '{module_id}' not found")

        module_dir = self.root / "modules" / validate_id(module_id, "module id")
        module_files = [p for p in self.storage.list_yaml(module_dir) if not p.name.startswith("_")]
        h = hashlib.sha256()
        for f in module_files:
            h.update(self.storage.read_bytes(f))
        content_hash = f"sha256:{h.hexdigest()}"

        # Try to get the current git SHA
        commit_sha = self.vcs.head_commit(self.root)

        module_manifest = self.modules[module_id]
        version = module_manifest.get("version", "1.0.0")
        ref = f"modules/{module_id}/v{version}"

        now = utcnow_iso()
        lock_entry = {
            "id": module_id,
            "version": version,
            "ref": ref,
            "sha": commit_sha,
            "content_hash": content_hash,
            "locked_at": now,
            "locked_by": locked_by,
        }

        lock_path = self.root / "products" / validate_id(product_id, "product id") / "_product.lock"
        if self.storage.exists(lock_path):
            try:
                existing = self.storage.read(lock_path)
                locked_list = existing.get("locked", [])
            except Exception:
                locked_list = []
        else:
            locked_list = []

        # Replace or add entry
        locked_list = [e for e in locked_list if e.get("id") != module_id]
        locked_list.append(lock_entry)

        lock_data = {
            "schema_version": "1.0.0",
            "generated_at": now,
            "generated_by": locked_by,
            "locked": locked_list,
        }
        self.storage.write(lock_path, lock_data)
        log.info("Lock written: %s (module %s)", lock_path, module_id)
        return lock_data

    def verify_module(self, product_id: str, module_id: str) -> dict[str, Any]:
        """Verify module files against the lock. Returns {verified, mismatch}."""
        import hashlib
        validate_id(module_id, "module id")
        lock_path = self.root / "products" / validate_id(product_id, "product id") / "_product.lock"
        if not self.storage.exists(lock_path):
            return {"verified": False, "reason": "lock file missing"}
        try:
            lock = self.storage.read(lock_path)
        except Exception as e:
            return {"verified": False, "reason": f"lock parse error: {e}"}

        locked = next((m for m in lock.get("locked", []) if m.get("id") == module_id), None)
        if not locked:
            return {"verified": False, "reason": f"module '{module_id}' not in lock"}

        module_dir = self.root / "modules" / validate_id(module_id, "module id")
        files = [p for p in self.storage.list_yaml(module_dir) if not p.name.startswith("_")]
        h = hashlib.sha256()
        for f in files:
            h.update(self.storage.read_bytes(f))
        computed = f"sha256:{h.hexdigest()}"

        if computed == locked.get("content_hash", ""):
            return {"verified": True, "module_id": module_id, "content_hash": computed}
        return {
            "verified": False,
            "reason": "content hash mismatch -- module files have changed since lock was generated",
            "stored": locked.get("content_hash"),
            "computed": computed,
        }

    # ------------------------------------------------------------------
    # UID search (for relationships editor)
    # ------------------------------------------------------------------

    def fetch_remote_module(self, module_id: str) -> dict[str, Any]:
        """Fetch an external Git repository module into modules/<module_id>/."""
        validate_id(module_id, "module id")

        manifest_path = self.root / "modules" / module_id / "_module.yaml"
        if not self.storage.exists(manifest_path):
            raise ValueError(f"Module manifest for '{module_id}' not found")
        data = self.storage.read(manifest_path)
        git_remote = str(data.get("git_remote", "")).strip()
        git_ref = str(data.get("git_ref", "main")).strip()
        if not git_remote:
            raise ValueError(f"Module '{module_id}' does not specify 'git_remote'")

        _validate_remote_url(git_remote)
        _validate_remote_ref(git_ref)

        target_dir = self.root / "modules" / module_id / "remote"
        self.vcs.fetch_checkout(git_remote, git_ref, target_dir, self.root)

        # Record exactly what was fetched, so a moving branch cannot change a module unnoticed (FEAT-08).
        commit = self.vcs.head_commit(target_dir)
        if commit and data.get("pinned_commit") != commit:
            data["pinned_commit"] = commit
            self.storage.write(manifest_path, data)

        self._load_modules()
        return {"status": "fetched", "module_id": module_id, "git_remote": git_remote, "git_ref": git_ref,
                "commit": commit}
