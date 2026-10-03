"""
reqtool.routers.auth
====================
Authentication & User Account REST endpoints.
Covers: /auth/login, /auth/me, /auth/users
"""

import re
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from reqtool.store import Store
from reqtool.routers.deps import get_store
from reqtool.auth import UserStore, create_token, verify_token

router = APIRouter(prefix="/auth", tags=["auth"])


def get_current_user(
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

    if token:
        payload = verify_token(token, store.root)
        if payload:
            users = UserStore(store.root).load_users()
            user = users.get(payload.get("sub", ""))
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


@router.post("/login")
def login(body: dict[str, Any], store: Store = Depends(get_store)):
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password required",
        )

    user = UserStore(store.root).authenticate(username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_token(user["username"], user["role"], store.root)
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
    password = str(body.get("password", "")).strip()
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
