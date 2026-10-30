"""Failures a use case reports, with the status and body a client receives (no web framework needed)."""

from __future__ import annotations

from typing import Any, Optional


class ServiceError(Exception):
    status = 400
    code = "error"

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra

    @property
    def detail(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, **self.extra}


class NotFound(ServiceError):
    status = 404
    code = "not_found"

    def __init__(self, uid: str, message: Optional[str] = None) -> None:
        super().__init__(message or f"UID '{uid}' not found", uid=uid)


class MissingItem(ServiceError):
    """A part of an item (for example an acceptance criterion) does not exist; the body has no ``uid``."""
    status = 404
    code = "not_found"


class Conflict(ServiceError):
    status = 409
    code = "conflict"


class MergeConflicts(Conflict):
    def __init__(self) -> None:
        super().__init__("Working tree has unresolved merge conflicts")


class NoGitIdentity(Conflict):
    code = "no_git_identity"


class VersionConflict(Conflict):
    code = "version_conflict"

    def __init__(self, yours: str, current: Optional[str]) -> None:
        super().__init__(
            f"Requirement was modified since you loaded it (your version: {yours}, current: {current}). "
            "Reload and re-apply your changes.",
            current_version=current, your_version=yours)


class WorkflowGuard(Conflict):
    code = "workflow_guard"


class StaleContent(Conflict):
    code = "stale_content"


class OpenTbd(Conflict):
    code = "open_tbd"


class Forbidden(ServiceError):
    status = 403
    code = "forbidden"


class Invalid(ServiceError):
    status = 422
    code = "validation"


class GitFailure(ServiceError):
    status = 500
    code = "git_error"
