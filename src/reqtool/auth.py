"""
reqtool.auth
============
User authentication, password hashing (PBKDF2-HMAC-SHA256), token generation,
and user management for multi-user server mode.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Optional
from reqtool.fileio import load_yaml, save_yaml, utcnow_iso

# Secret key file location
SECRET_FILE = ".secret_key"


SECRET_IGNORE_ENTRIES = (".reqtool/.secret_key", ".reqtool/users.yaml")


def ensure_secrets_ignored(repo_root: Path) -> None:
    """Make sure the key and user store can never be committed by accident.

    Appends any missing entries to ``<repo_root>/.gitignore`` (creating it if needed).
    """
    gi = repo_root / ".gitignore"
    try:
        existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
        lines = {ln.strip() for ln in existing.splitlines()}
        missing = [e for e in SECRET_IGNORE_ENTRIES if e not in lines]
        if missing:
            prefix = "" if not existing or existing.endswith("\n") else "\n"
            gi.write_text(existing + prefix + "\n".join(missing) + "\n", encoding="utf-8")
    except OSError:
        pass


def _restrict(path: Path) -> None:
    """Best-effort owner-only permissions (no-op where unsupported)."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _get_secret_key(repo_root: Path) -> bytes:
    sec_path = repo_root / ".reqtool" / SECRET_FILE
    if sec_path.exists():
        _restrict(sec_path)
        return sec_path.read_bytes()
    sec_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_secrets_ignored(repo_root)
    key = os.urandom(32)
    try:
        # O_EXCL + 0600: never world-readable, and two creators cannot clobber each other.
        fd = os.open(sec_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return sec_path.read_bytes()
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    return key


def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return key.hex(), salt.hex()


def verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    key, _ = hash_password(password, salt)
    return hmac.compare_digest(key, password_hash)


def create_token(username: str, role: str, repo_root: Path, expires_in: int = 86400 * 30) -> str:
    secret = _get_secret_key(repo_root)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "role": role,
        "exp": int(time.time()) + expires_in,
        "iat": int(time.time()),
    }
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_token(token: str, repo_root: Path) -> Optional[dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        secret = _get_secret_key(repo_root)

        # Pad base64 strings
        def _pad(s: str) -> str:
            return s + "=" * (-len(s) % 4)

        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(_pad(sig_b64))

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(base64.urlsafe_b64decode(_pad(payload_b64)).decode())
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def sign_approval(uid: str, version: int, username: str, repo_root: Path) -> str:
    """Generate an HMAC-SHA256 cryptographic signature for a requirement approval."""
    secret = _get_secret_key(repo_root)
    msg = f"APPROVE:{uid}:v{version}:{username}".encode("utf-8")
    sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    return f"SIG-v1-{sig[:32]}"


def verify_approval_signature(uid: str, version: int, username: str, signature: str, repo_root: Path) -> bool:
    """Verify an HMAC-SHA256 cryptographic approval signature."""
    expected = sign_approval(uid, version, username, repo_root)
    return hmac.compare_digest(signature, expected)


class UserStore:
    def __init__(self, root: Path):
        self.root = root
        self.users_file = root / ".reqtool" / "users.yaml"

    def load_users(self) -> dict[str, dict[str, Any]]:
        if not self.users_file.exists():
            # Seed default admin user
            self._seed_default_admin()
        data = load_yaml(self.users_file) or {}
        return data.get("users", {})

    def _seed_default_admin(self):
        self.users_file.parent.mkdir(parents=True, exist_ok=True)
        h, salt = hash_password("admin123")
        default_data = {
            "users": {
                "admin": {
                    "username": "admin",
                    "full_name": "Administrator",
                    "email": "admin@reqtool.local",
                    "role": "admin",
                    "password_hash": h,
                    "salt": salt,
                    "created": utcnow_iso(),
                }
            }
        }
        ensure_secrets_ignored(self.root)
        save_yaml(self.users_file, default_data)
        _restrict(self.users_file)

    def save_users(self, users: dict[str, dict[str, Any]]):
        self.users_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.users_file, {"users": users})
        _restrict(self.users_file)

    def authenticate(self, username: str, password: str) -> Optional[dict[str, Any]]:
        users = self.load_users()
        user = users.get(username)
        if not user:
            return None
        if verify_password(password, user.get("password_hash", ""), user.get("salt", "")):
            return user
        return None

    def create_user(self, username: str, password: str, full_name: str = "", email: str = "", role: str = "editor") -> dict[str, Any]:
        users = self.load_users()
        if username in users:
            raise ValueError(f"User '{username}' already exists")
        h, salt = hash_password(password)
        user_record = {
            "username": username,
            "full_name": full_name or username.title(),
            "email": email,
            "role": role if role in ("admin", "editor", "viewer") else "editor",
            "password_hash": h,
            "salt": salt,
            "created": utcnow_iso(),
        }
        users[username] = user_record
        self.save_users(users)
        return user_record

    def update_user(self, username: str, updates: dict[str, Any]) -> dict[str, Any]:
        users = self.load_users()
        if username not in users:
            raise KeyError(f"User '{username}' not found")
        u = users[username]
        if "password" in updates and updates["password"]:
            h, salt = hash_password(updates["password"])
            u["password_hash"] = h
            u["salt"] = salt
        if "full_name" in updates:
            u["full_name"] = updates["full_name"]
        if "email" in updates:
            u["email"] = updates["email"]
        if "role" in updates and updates["role"] in ("admin", "editor", "viewer"):
            u["role"] = updates["role"]
        users[username] = u
        self.save_users(users)
        return u
