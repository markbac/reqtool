"""
reqtool.routers.auth
====================
Authentication & User Account REST endpoints.
Covers: /auth/login, /auth/me, /auth/users
"""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Header, status
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


@router.get("/users")
def list_users(
    user: dict[str, Any] = Depends(get_current_user),
    store: Store = Depends(get_store),
):
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
    user: dict[str, Any] = Depends(get_current_user),
    store: Store = Depends(get_store),
):
    if user["authenticated"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to create users")

    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    try:
        new_user = UserStore(store.root).create_user(
            username=username,
            password=password,
            full_name=body.get("full_name", ""),
            email=body.get("email", ""),
            role=body.get("role", "editor"),
        )
        return {
            "username": new_user["username"],
            "full_name": new_user["full_name"],
            "role": new_user["role"],
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
