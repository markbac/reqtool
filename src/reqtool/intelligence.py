"""
reqtool.intelligence
====================
AI Intelligence, Duplicate Detector, Test Generator, Audit Package Exporter, and OSLC/SysML Linkage.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from reqtool.store import Store
from reqtool.fileio import utcnow_iso, save_yaml


def detect_duplicate_requirements(store: Store, threshold: float = 0.5) -> list[dict[str, Any]]:
    """Scan all requirements and detect potential duplicates/overlaps using word token similarity."""
    reqs = list(store.requirements.values())
    duplicates = []

    def _tokenize(text: str) -> set[str]:
        words = re.findall(r'\w+', text.lower())
        return set(w for w in words if len(w) > 3)

    for i in range(len(reqs)):
        for j in range(i + 1, len(reqs)):
            r1, r2 = reqs[i], reqs[j]
            t1 = _tokenize(f"{r1.get('title','')} {r1.get('content',{}).get('description','')}")
            t2 = _tokenize(f"{r2.get('title','')} {r2.get('content',{}).get('description','')}")

            if not t1 or not t2:
                continue

            intersection = t1.intersection(t2)
            union = t1.union(t2)
            similarity = len(intersection) / len(union) if union else 0.0

            if similarity >= threshold:
                duplicates.append({
                    "req_a": {"uid": r1["uid"], "id": r1["id"], "title": r1["title"]},
                    "req_b": {"uid": r2["uid"], "id": r2["id"], "title": r2["title"]},
                    "similarity_score": round(similarity, 2),
                    "overlapping_terms": list(intersection)[:8],
                })

    return sorted(duplicates, key=lambda x: -x["similarity_score"])


def generate_test_cases_from_spec(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    """Auto-generate verification test procedure steps from requirement specification."""
    req_id = requirement.get("id", "REQ-001")
    title = requirement.get("title", "")
    description = requirement.get("content", {}).get("description", "")
    ac_list = requirement.get("acceptance_criteria", [])

    tests = []
    # Test 1: Positive verification procedure
    tests.append({
        "test_id": f"TEST-POS-{req_id}",
        "title": f"Positive Verification Test for {title}",
        "verification_type": "test",
        "preconditions": [f"System is initialized in nominal state for {req_id}"],
        "test_steps": [
            f"1. Configure input parameters for {title}",
            f"2. Execute action specified in: {description[:60]}...",
            "3. Observe system output response and status flags",
        ],
        "expected_result": f"System output satisfies criteria: {title}",
    })

    # Test 2: AC-driven test cases
    for idx, ac in enumerate(ac_list, 1):
        tests.append({
            "test_id": f"TEST-AC-{ac.get('id', idx)}",
            "title": f"Acceptance Test: {ac.get('text', '')[:40]}",
            "verification_type": "demonstration",
            "preconditions": ["Acceptance criteria test environment configured"],
            "test_steps": [
                f"1. Apply inputs corresponding to criterion {ac.get('id', idx)}",
                "2. Verify status transition and log assertion",
            ],
            "expected_result": f"Criterion passed: {ac.get('text', '')}",
        })

    return tests


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
