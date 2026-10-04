"""Audit package: a zip of the repository state for an external reviewer."""

from __future__ import annotations

import io
import json
import zipfile

from typing import Iterable, Optional

from reqtool.store import Store
from reqtool.fileio import utcnow_iso


CONTENT = ("signatures", "requirements", "traceability", "history", "validation", "decisions")
DEFAULT_CONTENT = ("signatures", "requirements")
SCOPES = ("repository", "product", "module", "selection")


class AuditScopeError(ValueError):
    pass


def _scoped(store: Store, scope: str, product: Optional[str], module: Optional[str],
            uids: Optional[Iterable[str]]) -> dict[str, dict]:
    if scope not in SCOPES:
        raise AuditScopeError(f"scope must be one of {', '.join(SCOPES)}")
    if scope == "repository":
        return dict(store.requirements)
    if scope == "product":
        if product not in store.products:
            raise AuditScopeError(f"Product '{product}' not found")
        return dict(store.resolved_requirements(product))
    if scope == "module":
        if module not in store.modules:
            raise AuditScopeError(f"Module '{module}' not found")
        return dict(store.module_requirements.get(module, {}))
    wanted = set(uids or [])
    if not wanted:
        raise AuditScopeError("selection scope needs at least one uid")
    return {u: r for u, r in store.requirements.items() if u in wanted}


def generate_audit_package(store: Store, scope: str = "repository", product: Optional[str] = None,
                           module: Optional[str] = None, uids: Optional[Iterable[str]] = None,
                           include: Optional[Iterable[str]] = None) -> bytes:
    """Zipped 21 CFR Part 11 / ISO 26262 audit package for a scope, with the parts the caller selects (ENH-07)."""
    include = tuple(include) if include is not None else DEFAULT_CONTENT
    unknown = [c for c in include if c not in CONTENT]
    if unknown:
        raise AuditScopeError("unknown content: " + ", ".join(unknown))
    reqs = _scoped(store, scope, product, module, uids)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "dossier_type": "ISO 26262 / 21 CFR Part 11 Regulatory Compliance Package",
            "generated_at": utcnow_iso(),
            "repo_id": store.config.repo_id,
            "repo_title": store.config.repo_title,
            "scope": scope, "product": product, "module": module,
            "content": list(include),
            "total_requirements": len(reqs),
            "total_principles": len(store.principles),
        }
        zf.writestr("audit_manifest.json", json.dumps(manifest, indent=2))
        if "signatures" in include:
            signatures = []
            for req in reqs.values():
                app = req.get("approval", {})
                if app.get("signature"):
                    signatures.append({"uid": req["uid"], "id": req["id"], "title": req["title"],
                                       "approved_by": app.get("approved_by"), "approved_date": app.get("approved_date"),
                                       "signature": app.get("signature")})
            zf.writestr("cryptographic_signatures.json", json.dumps(signatures, indent=2))
        if "requirements" in include:
            zf.writestr("requirements_dump.json", json.dumps(list(reqs.values()), indent=2))
        if "traceability" in include:
            from reqtool.features.insight import requirement_trace
            trace = [t for u in reqs if (t := requirement_trace(store, u))] if scope != "module" else []
            zf.writestr("traceability.json", json.dumps(trace, indent=2))
        if "history" in include:
            zf.writestr("history.json", json.dumps(
                {r.get("id") or u: r.get("history", []) for u, r in reqs.items()}, indent=2))
        if "validation" in include:
            from reqtool.validation import validate_all
            zf.writestr("validation.json", json.dumps(validate_all(store), indent=2, default=str))
        if "decisions" in include:
            zf.writestr("decisions.json", json.dumps(store.live_decision_records(), indent=2, default=str))
    buffer.seek(0)
    return buffer.getvalue()
