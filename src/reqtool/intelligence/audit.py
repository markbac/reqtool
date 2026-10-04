"""Audit package: a zip of the repository state for an external reviewer."""

from __future__ import annotations

import io
import json
import zipfile

from reqtool.store import Store
from reqtool.fileio import utcnow_iso


def generate_audit_package(store: Store) -> bytes:
    """Generate zipped 21 CFR Part 11 / ISO 26262 Regulatory Compliance Audit Package."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Audit manifest
        manifest = {
            "dossier_type": "ISO 26262 / 21 CFR Part 11 Regulatory Compliance Package",
            "generated_at": utcnow_iso(),
            "repo_id": store.config.repo_id,
            "repo_title": store.config.repo_title,
            "total_requirements": len(store.requirements),
            "total_principles": len(store.principles),
        }
        zf.writestr("audit_manifest.json", json.dumps(manifest, indent=2))

        # 2. Cryptographic signature ledger
        signatures = []
        for req in store.requirements.values():
            app = req.get("approval", {})
            if app.get("signature"):
                signatures.append({
                    "uid": req["uid"],
                    "id": req["id"],
                    "title": req["title"],
                    "approved_by": app.get("approved_by"),
                    "approved_date": app.get("approved_date"),
                    "signature": app.get("signature"),
                })
        zf.writestr("cryptographic_signatures.json", json.dumps(signatures, indent=2))

        # 3. Complete Requirements Dump
        zf.writestr("requirements_dump.json", json.dumps(list(store.requirements.values()), indent=2))

    buffer.seek(0)
    return buffer.getvalue()
