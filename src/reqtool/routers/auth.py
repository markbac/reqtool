"""
reqtool.routers.auth
====================
Authentication & User Account REST endpoints.
Covers: /auth/login, /auth/me, /auth/users
"""

import re
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response, status
from fastapi.responses import JSONResponse
from reqtool.store import Store
from reqtool.routers.deps import get_store
from reqtool.auth import (
    CSRF_HEADER, REFRESH_COOKIE, REFRESH_LIFETIME, SESSION_COOKIE, SESSION_LIFETIME,
    UserStore, create_token, login_throttle,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_current_user(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    """Extract authenticated user from Authorization Bearer token or fallback to anonymous user."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token:
        token = request.cookies.get(SESSION_COOKIE)
    if token:
        user = UserStore(store.root).resolve_token(token)
        if user:
            return {
                "username": user["username"],
                "full_name": user.get("full_name", user["username"]),
                "email": user.get("email", ""),
                "role": user.get("role", "editor"),
                "authenticated": True,
            }

    # Fallback default for local single-user mode
    return {
        "username": "user",
        "full_name": "Local User",
        "email": "",
        "role": "admin",
        "authenticated": False,
    }


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _set_session(response: Response, request: Request, user: dict[str, Any], store: Store,
                 auth_at: int | None = None) -> None:
    """Browser session: a short-lived access cookie and a longer refresh cookie, both HttpOnly and SameSite=Strict."""
    tv = user.get("token_version", 0)
    secure = _secure(request)
    response.set_cookie(SESSION_COOKIE, create_token(user["username"], user["role"], store.root, SESSION_LIFETIME,
                                                     tv, "access", auth_at),
                        max_age=SESSION_LIFETIME, path="/", httponly=True, samesite="strict", secure=secure)
    # The refresh cookie is only sent to /auth, so ordinary requests never carry it.
    response.set_cookie(REFRESH_COOKIE, create_token(user["username"], user["role"], store.root, REFRESH_LIFETIME,
                                                     tv, "refresh", auth_at),
                        max_age=REFRESH_LIFETIME, path="/auth", httponly=True, samesite="strict", secure=secure)


def _require_csrf_header(request: Request) -> None:
    if not request.headers.get(CSRF_HEADER):
        raise HTTPException(status_code=403, detail={"error": "csrf", "message": f"Missing {CSRF_HEADER} header"})


@router.post("/login")
def login(body: dict[str, Any], request: Request, response: Response, store: Store = Depends(get_store)):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))  # passwords are used exactly as typed

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password required",
        )

    keys = (f"user:{username.lower()}", f"ip:{request.client.host if request.client else ''}")
    wait = login_throttle.retry_after(*keys)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "message": f"Too many failed logins; try again in {wait} seconds"},
            headers={"Retry-After": str(wait)},
        )
    user = UserStore(store.root).authenticate(username, password)
    if not user:
        login_throttle.record_failure(*keys)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    login_throttle.reset(keys[0])  # a success clears the account's counter (the address keeps its own)
    # Bearer token for scripts and API clients. The browser UI ignores it and uses the cookies set here.
    token = create_token(user["username"], user["role"], store.root, token_version=user.get("token_version", 0))
    _set_session(response, request, user, store)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user.get("full_name", user["username"]),
            "email": user.get("email", ""),
            "role": user["role"],
        },
    }


@router.post("/refresh")
def refresh(request: Request, response: Response, store: Store = Depends(get_store)):
    """Exchange the refresh cookie for a new access cookie (and a rotated refresh cookie)."""
    _require_csrf_header(request)
    found = UserStore(store.root).resolve_refresh(request.cookies.get(REFRESH_COOKIE))
    if not found:
        expired = JSONResponse(status_code=401, content={"detail": {"error": "unauthorized",
                               "message": "Session expired, please log in again"}})
        expired.delete_cookie(SESSION_COOKIE, path="/")
        expired.delete_cookie(REFRESH_COOKIE, path="/auth")
        return expired
    user, claims = found
    _set_session(response, request, user, store, auth_at=int(claims.get("auth_at", 0)) or None)
    return {"status": "refreshed"}


@router.post("/logout")
def logout(request: Request, response: Response):
    """End the browser session by clearing both cookies."""
    _require_csrf_header(request)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/auth")
    return {"status": "logged_out"}


@router.get("/me")
def get_me(user: dict[str, Any] = Depends(get_current_user)):
    return user


_USERNAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}")
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@router.get("/users")
def list_users(
    user: dict[str, Any] = Depends(get_current_user),
    store: Store = Depends(get_store),
):
    if not user["authenticated"]:
        raise HTTPException(status_code=401, detail="Login required")
    users = UserStore(store.root).load_users()
    result = []
    for u in users.values():
        result.append({
            "username": u["username"],
            "full_name": u.get("full_name", u["username"]),
            "email": u.get("email", ""),
            "role": u.get("role", "editor"),
            "created": u.get("created", ""),
        })
    return result


@router.post("/users", status_code=201)
def create_user(
    body: dict[str, Any],
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    store: Store = Depends(get_store),
):
    """Create an account.

    Only an authenticated administrator may create users. The single exception
    is bootstrap: while NO accounts exist, a request from the local machine may
    create the first one, which is always an administrator.
    """
    users = UserStore(store.root)
    bootstrap = not users.has_users()
    if bootstrap:
        host = request.client.host if request.client else ""
        if host not in _LOCAL_HOSTS:
            raise HTTPException(status_code=403, detail="The first account must be created from the local machine (or with `req user add`)")
    elif not (user["authenticated"] and user["role"] == "admin"):
        raise HTTPException(
            status_code=401 if not user["authenticated"] else 403,
            detail="Administrator login required to create users",
        )

    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if not _USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=422, detail="Invalid username")
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    role = "admin" if bootstrap else body.get("role", "editor")
    if role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=422, detail="Invalid role")

    try:
        new_user = users.create_user(
            username=username,
            password=password,
            full_name=body.get("full_name", ""),
            email=body.get("email", ""),
            role=role,
        )
        return {
            "username": new_user["username"],
            "full_name": new_user["full_name"],
            "role": new_user["role"],
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
