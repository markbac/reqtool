"""
reqtool.routers.lint
====================
Writing checks (glossary, wordy phrases, acronyms, vague terms, Vale) and their settings.
Changing the settings is for administrators (see ``permissions``).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from reqtool.services.lint import LintService
from reqtool.store import Store
from .deps import ReqUid, get_store

router = APIRouter(tags=["lint"])


def get_service(store: Store = Depends(get_store)) -> LintService:
    return LintService(store)


@router.get("/lint/config")
def get_lint_config(service: LintService = Depends(get_service)):
    """The repository's lint settings (every setting, defaults filled in), rule list and Vale status."""
    return service.describe()


@router.put("/lint/config")
def save_lint_config(body: dict[str, Any], service: LintService = Depends(get_service)):
    return service.save(body)


@router.post("/lint/text")
def lint_text(body: dict[str, Any], service: LintService = Depends(get_service)):
    """Check a piece of Markdown, for example what is being typed in the editor."""
    return service.lint_text(str(body.get("text", "")))


@router.get("/lint")
def lint_all(
    severity: Literal["error", "warning", "info"] = "info",
    limit: int = Query(500, ge=1, le=5000),
    service: LintService = Depends(get_service),
):
    """Check every item. ``severity`` is the least serious level to include."""
    return service.lint_all(severity, limit)


@router.get("/requirements/{uid}/lint")
def lint_requirement(uid: ReqUid, service: LintService = Depends(get_service)):
    return service.lint_requirement(uid)
