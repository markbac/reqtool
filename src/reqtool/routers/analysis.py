"""
reqtool.routers.analysis
========================
FastAPI router for validation endpoints.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends

from reqtool.store import Store
from reqtool.validation import validate_all, validate_single
from .deps import get_store

log = logging.getLogger(__name__)

router = APIRouter(tags=["validation"])


@router.get("/validate")
def run_validation(store: Store = Depends(get_store)):
    return validate_all(store)


@router.get("/validate/{uid}")
def validate_artefact(uid: str, store: Store = Depends(get_store)):
    return validate_single(store, uid)


@router.post("/analysis/generate-ac")
def generate_ac_scenarios(payload: dict):
    title = payload.get("title", "Requirement action")
    description = payload.get("description", "")
    req_type = payload.get("req_type", "functional")

    subject = "the user" if ("user" in title.lower() or "user" in description.lower()) else "the system"

    scenarios = [
        {
            "id": "AC-001",
            "scenario_title": f"Successful execution of {title}",
            "given": f"{subject.capitalize()} is authenticated and on the active workspace",
            "when": f"{subject} triggers '{title}'",
            "then": "The system processes the operation and updates the repository state",
            "text": f"Scenario 1: Successful execution of {title}\n  Given {subject.capitalize()} is authenticated\n  When {subject} triggers '{title}'\n  Then the system processes the operation successfully",
        },
        {
            "id": "AC-002",
            "scenario_title": f"Validation and error handling for {title}",
            "given": "Invalid inputs or invalid preconditions are present",
            "when": f"{subject} attempts '{title}'",
            "then": "The system rejects the operation with a clear error notification",
            "text": f"Scenario 2: Validation and error handling\n  Given invalid inputs are provided\n  When {subject} attempts '{title}'\n  Then the system returns a validation error",
        },
    ]
    return {"status": "ok", "scenarios": scenarios}


from reqtool.intelligence import detect_duplicate_requirements, generate_test_cases_from_spec
from fastapi import HTTPException

@router.get("/analysis/detect-duplicates")
def detect_duplicates(threshold: float = 0.4, store: Store = Depends(get_store)):
    return detect_duplicate_requirements(store, threshold=threshold)


@router.post("/analysis/generate-tests/{uid}")
def generate_tests(uid: str, store: Store = Depends(get_store)):
    req = store.get_requirement(uid)
    if not req:
        raise HTTPException(status_code=404, detail=f"Requirement '{uid}' not found")
    tests = generate_test_cases_from_spec(req)
    return {"uid": uid, "test_cases": tests}

