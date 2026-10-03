"""
reqtool.security
================
Access control for the HTTP API and WebSocket.

Two modes, chosen with ``REQTOOL_AUTH`` / ``req serve --auth``:

``local`` (default)
    Single-user desktop use. No login, but ONLY loopback clients are served;
    anything else is refused with 403. ``req serve`` refuses to bind a
    non-loopback address in this mode.

``required``
    Every API call needs a valid token (``Authorization: Bearer``, ``X-API-Key``,
    or ``access_token`` query parameter on GET for browser downloads). Viewers
    are read-only and configuration/repository endpoints are admin-only.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
MODES = ("local", "required")

# Reachable without a token in `required` mode.
PUBLIC_PATHS = {"/health", "/version", "/auth/login"}
# Authenticated by its own HMAC signature instead of a login token.
SIGNED_PATHS = {"/webhooks/github"}
PUBLIC_PREFIXES = ("/badge/", "/assets/")
STATIC_SUFFIXES = (".js", ".css", ".map", ".ico", ".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ttf")

# (method, path prefix) pairs that need the admin role in `required` mode.
ADMIN_ONLY: tuple[tuple[Optional[str], str], ...] = (
    (None, "/repo/"),
    ("PUT", "/config"),
    ("PUT", "/workflow"),
    ("PUT", "/enums/repo"),
    ("PUT", "/custom-fields"),
    ("POST", "/webhooks"),
    ("DELETE", "/webhooks"),
    ("POST", "/auth/users"),
)


def resolve_mode(explicit: Optional[str] = None) -> str:
    mode = (explicit or os.environ.get("REQTOOL_AUTH") or "local").strip().lower()
    if mode not in MODES:
        raise ValueError(f"Invalid authentication mode '{mode}' (expected one of {MODES})")
    return mode


def is_loopback_host(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost") or host.startswith("127.")


def is_public_path(method: str, path: str) -> bool:
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return True
    if method in ("GET", "HEAD") and (path in ("/", "/index.html") or path.endswith(STATIC_SUFFIXES)):
        return True
    return False


def extract_token(request_headers, query_params, method: str) -> Optional[str]:
    auth = request_headers.get("authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip()
    key = request_headers.get("x-api-key")
    if key:
        return key.strip()
    if method in ("GET", "HEAD"):
        return query_params.get("access_token")
    return None


def user_for_token(token: Optional[str], root: Path) -> Optional[dict[str, Any]]:
    """Resolve a token to a CURRENT user record (deleted users stop working immediately)."""
    if not token:
        return None
    from .auth import UserStore, verify_token
    payload = verify_token(token, root)
    if not payload:
        return None
    user = UserStore(root).load_users().get(payload.get("sub", ""))
    if not user:
        return None
    return {
        "username": user["username"],
        "role": user.get("role", "editor"),
    }


def _deny(status: int, error: str, message: str) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(status_code=status, content={"detail": {"error": error, "message": message}}, headers=headers)


def install(app, mode: str) -> None:
    """Register the access-control middleware on ``app``."""
    app.state.auth_mode = mode

    @app.middleware("http")
    async def access_control(request: Request, call_next):
        method, path = request.method, request.url.path
        if method == "OPTIONS":  # CORS preflight carries no credentials
            return await call_next(request)
        host = request.client.host if request.client else ""

        if method == "POST" and path in SIGNED_PATHS:
            return await call_next(request)

        if mode == "local":
            if path == "/health" or host in LOCAL_HOSTS or is_loopback_host(host):
                return await call_next(request)
            return _deny(403, "forbidden",
                         "This server is in local mode and only accepts connections from this machine. "
                         "Start it with `--auth required` to allow remote users.")

        # mode == "required"
        # First-account bootstrap: allowed unauthenticated; the handler itself
        # insists on loopback and an empty user table.
        if method == "POST" and path == "/auth/users" and not _has_users(app):
            return await call_next(request)
        if is_public_path(method, path):
            return await call_next(request)
        user = user_for_token(extract_token(request.headers, request.query_params, method), app.state.store.root)
        if user is None:
            return _deny(401, "unauthorized", "Authentication required")
        if user["role"] == "viewer" and method not in ("GET", "HEAD"):
            return _deny(403, "forbidden", "Your role is read-only")
        if user["role"] != "admin":
            for m, prefix in ADMIN_ONLY:
                if (m is None or m == method) and (path == prefix.rstrip("/") or path.startswith(prefix)):
                    return _deny(403, "forbidden", "Administrator role required")
        return await call_next(request)


def _has_users(app) -> bool:
    from .auth import UserStore
    return UserStore(app.state.store.root).has_users()


def websocket_allowed(websocket, mode: str, root: Path) -> bool:
    """Gate for /ws (HTTP middleware does not see WebSocket connections)."""
    host = websocket.client.host if websocket.client else ""
    if mode == "local":
        return host in LOCAL_HOSTS or is_loopback_host(host)
    token = extract_token(websocket.headers, websocket.query_params, "GET") or websocket.query_params.get("token")
    return user_for_token(token, root) is not None
