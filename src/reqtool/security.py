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

from .actor import current_actor, current_role
from .auth import CSRF_HEADER, SESSION_COOKIE

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
MODES = ("local", "required")

# Reachable without a token in `required` mode.
PUBLIC_PATHS = {"/health", "/version", "/auth/login", "/auth/refresh", "/auth/logout"}
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


def _hostname(value: str) -> str:
    """Host part of a ``Host`` header or an Origin URL, without scheme or port."""
    value = value.split("://", 1)[-1].split("/", 1)[0]
    if value.startswith("["):  # IPv6 literal
        return value[1:].split("]", 1)[0].lower()
    return value.rsplit(":", 1)[0].lower() if value.count(":") == 1 else value.lower()


def _allowed_local_names() -> set[str]:
    extra = {h.strip().lower() for h in os.environ.get("REQTOOL_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return {"localhost", "testserver", "testclient"} | extra


def local_request_problem(headers, method: str) -> Optional[str]:
    """Why a local-mode request must be refused although it came from loopback, else None.

    Loopback alone does not stop a web page in the user's browser: DNS rebinding makes
    ``evil.example`` resolve to 127.0.0.1, and a cross-site form can POST here. So the
    ``Host`` must name this machine and a browser ``Origin`` must too.
    """
    names = _allowed_local_names()

    def local(name: str) -> bool:
        return bool(name) and (is_loopback_host(name) or name in names)

    host = headers.get("host")
    if host and not local(_hostname(host)):
        return f"Host '{host}' is not this machine (possible DNS rebinding)"
    origin = headers.get("origin")
    if origin and method not in ("GET", "HEAD", "OPTIONS") and not local(_hostname(origin)):
        return f"Cross-site request from origin '{origin}' refused"
    return None


def is_public_path(method: str, path: str) -> bool:
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return True
    # Only top-level UI files (favicon, logo) are public. A deeper path such as
    # /requirements/{uid}/attachments/x.png is an API route and needs a token.
    if method in ("GET", "HEAD") and (path in ("/", "/index.html")
                                      or (path.count("/") == 1 and path.endswith(STATIC_SUFFIXES))):
        return True
    return False


def extract_credentials(request_headers, query_params, method: str, cookies=None) -> tuple[Optional[str], str]:
    """The token a request carries and where it came from: ``header``, ``query``, ``cookie`` or ``none``."""
    auth = request_headers.get("authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip(), "header"
    key = request_headers.get("x-api-key")
    if key:
        return key.strip(), "header"
    if method in ("GET", "HEAD") and query_params.get("access_token"):
        return query_params.get("access_token"), "query"
    if cookies and cookies.get(SESSION_COOKIE):
        return cookies.get(SESSION_COOKIE), "cookie"
    return None, "none"


def extract_token(request_headers, query_params, method: str, cookies=None) -> Optional[str]:
    return extract_credentials(request_headers, query_params, method, cookies)[0]


def csrf_header_present(headers) -> bool:
    return bool(headers.get(CSRF_HEADER))


def user_for_token(token: Optional[str], root: Path) -> Optional[dict[str, Any]]:
    """Resolve a token to a CURRENT user record (deleted users stop working immediately)."""
    if not token:
        return None
    from .auth import UserStore
    user = UserStore(root).resolve_token(token)
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
                problem = None if path == "/health" else local_request_problem(request.headers, method)
                if problem:
                    return _deny(403, "forbidden", problem)
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
        token, source = extract_credentials(request.headers, request.query_params, method, request.cookies)
        user = user_for_token(token, app.state.store.root)
        if user is None:
            return _deny(401, "unauthorized", "Authentication required")
        if source == "cookie" and method not in ("GET", "HEAD") and not csrf_header_present(request.headers):
            # Browser sessions ride on a cookie, so a state-changing request must also carry the custom header
            # that only our own pages can add. Bearer-token clients are not affected.
            return _deny(403, "csrf", f"Cookie sessions need the {CSRF_HEADER} header on {method} requests")
        if user["role"] == "viewer" and method not in ("GET", "HEAD"):
            return _deny(403, "forbidden", "Your role is read-only")
        if user["role"] != "admin":
            for m, prefix in ADMIN_ONLY:
                if (m is None or m == method) and (path == prefix.rstrip("/") or path.startswith(prefix)):
                    return _deny(403, "forbidden", "Administrator role required")
        # Record who is acting so history, comments and attachments carry the real user.
        actor_token = current_actor.set(user["username"])
        role_token = current_role.set(user["role"])
        try:
            return await call_next(request)
        finally:
            current_actor.reset(actor_token)
            current_role.reset(role_token)


def _has_users(app) -> bool:
    from .auth import UserStore
    return UserStore(app.state.store.root).has_users()


def websocket_allowed(websocket, mode: str, root: Path) -> bool:
    """Gate for /ws (HTTP middleware does not see WebSocket connections)."""
    host = websocket.client.host if websocket.client else ""
    if mode == "local":
        if not (host in LOCAL_HOSTS or is_loopback_host(host)):
            return False
        # A WebSocket handshake always carries Origin for browsers, so check it like a write.
        return local_request_problem(websocket.headers, "WEBSOCKET") is None
    token, source = extract_credentials(websocket.headers, websocket.query_params, "GET", websocket.cookies)
    token = token or websocket.query_params.get("token")
    if source == "cookie":
        # Browsers do not apply the same-origin policy to WebSockets: refuse a page on another origin.
        origin, host = websocket.headers.get("origin"), websocket.headers.get("host")
        if origin and host and origin.split("://", 1)[-1] != host:
            return False
    return user_for_token(token, root) is not None
