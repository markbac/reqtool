"""Test-case skeletons generated from a requirement's acceptance criteria."""

from __future__ import annotations

from typing import Any


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
