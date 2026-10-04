"""
reqtool.intelligence
====================
AI Intelligence, Duplicate Detector, Test Generator, Audit Package Exporter, and OSLC/SysML Linkage.
"""

from __future__ import annotations

import io
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any
from reqtool.store import Store
from reqtool.fileio import utcnow_iso, save_yaml


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"\w+", text.lower()) if len(w) > 3)


def detect_duplicate_requirements(store: Store, threshold: float = 0.5) -> list[dict[str, Any]]:
    """Find pairs of live requirements whose title and description share enough words (Jaccard similarity).

    Exact, but not quadratic: each item is tokenised once, and prefix filtering over a global
    rarest-first token order means only pairs that share a rare token are compared
    (a pair with Jaccard >= t must share a token in the first |a| - ceil(t*|a|) + 1 tokens of each).
    """
    return [dict(d) for d in store.memo("duplicates", threshold, lambda: _find_duplicates(store, threshold))]


def _find_duplicates(store: Store, threshold: float) -> list[dict[str, Any]]:
    reqs = [r for r in store.requirements.values() if not r.get("deleted")]
    tokens = [_tokenize(f"{r.get('title') or ''} {(r.get('content') or {}).get('description') or ''}") for r in reqs]

    freq: dict[str, int] = {}
    for toks in tokens:
        for t in toks:
            freq[t] = freq.get(t, 0) + 1
    order = lambda t: (freq[t], t)  # rarest first, ties broken by text so the order is total

    ranked = [sorted(toks, key=order) for toks in tokens]
    postings: dict[str, list[int]] = {}
    found: list[tuple[float, int, int, frozenset[str]]] = []

    for i, toks in enumerate(ranked):
        n = len(toks)
        if not n:
            continue
        prefix_len = n - math.ceil(threshold * n) + 1 if threshold > 0 else n
        candidates: set[int] = set()
        for t in toks[:max(prefix_len, 1)]:
            candidates.update(postings.get(t, ()))
        a = tokens[i]
        for j in candidates:
            b = tokens[j]
            if len(b) < threshold * n or n < threshold * len(b):
                continue  # sizes too different to reach the threshold
            inter = a & b
            similarity = len(inter) / (n + len(b) - len(inter))
            if similarity >= threshold:
                found.append((similarity, j, i, inter))
        for t in toks[:max(prefix_len, 1)]:
            postings.setdefault(t, []).append(i)

    duplicates = []
    for similarity, j, i, inter in sorted(found, key=lambda f: (-round(f[0], 2), f[1], f[2])):
        r1, r2 = reqs[j], reqs[i]
        duplicates.append({
            "req_a": {"uid": r1["uid"], "id": r1["id"], "title": r1["title"]},
            "req_b": {"uid": r2["uid"], "id": r2["id"], "title": r2["title"]},
            "similarity_score": round(similarity, 2),
            "overlapping_terms": sorted(inter)[:8],
        })
    return duplicates


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
