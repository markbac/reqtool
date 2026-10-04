"""
reqtool.auth
============
User authentication, password hashing (PBKDF2-HMAC-SHA256), token generation,
and user management for multi-user server mode.
"""

from __future__ import annotations

import hashlib
import logging
import hmac
import os
import time
from pathlib import Path
from typing import Any, Optional
from reqtool.fileio import load_yaml, save_yaml, utcnow_iso

log = logging.getLogger(__name__)

# Secret key file location
SECRET_FILE = ".secret_key"

# Credentials that older releases seeded into every new repository. They are
# publicly documented, so they are refused at login (see UserStore.authenticate).
LEGACY_DEFAULT_USER = "admin"
LEGACY_DEFAULT_PASSWORD = "admin123"


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


MIN_SECRET_BYTES = 32


def _read_valid_secret(sec_path: Path) -> Optional[bytes]:
    try:
        key = sec_path.read_bytes()
    except OSError:
        return None
    return key if len(key) >= MIN_SECRET_BYTES else None


def _get_secret_key(repo_root: Path) -> bytes:
    sec_path = repo_root / ".reqtool" / SECRET_FILE
    if sec_path.exists():
        _restrict(sec_path)
        key = _read_valid_secret(sec_path)
        if key is not None:
            return key
        # Empty or truncated (a crash between create and write): replace it rather than
        # signing with a weak key or failing every login.
        log.warning("Secret key file %s is invalid; generating a new one (existing tokens stop working).", sec_path)
        sec_path.unlink(missing_ok=True)
    sec_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_secrets_ignored(repo_root)
    key = os.urandom(32)
    # Write a complete 0600 temp file, then link it into place: the key file either does not
    # exist or is complete, and two creators cannot clobber each other.
    tmp = sec_path.with_name(f".{SECRET_FILE}.{os.getpid()}.{os.urandom(4).hex()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    try:
        os.link(tmp, sec_path)
    except FileExistsError:
        existing = _read_valid_secret(sec_path)
        if existing is not None:
            return existing
        os.replace(tmp, sec_path)
        return key
    finally:
        tmp.unlink(missing_ok=True)
    return key


PBKDF2_ITERATIONS = 600_000        # current OWASP guidance for PBKDF2-HMAC-SHA256
LEGACY_ITERATIONS = 100_000        # hashes written before the count was stored
TOKEN_LIFETIME = 12 * 3600         # seconds; bearer tokens for scripts and API clients
SESSION_LIFETIME = 30 * 60         # browser access cookie
REFRESH_LIFETIME = 7 * 24 * 3600   # browser refresh cookie
SESSION_MAX_AGE = 30 * 24 * 3600   # refreshing never extends a login beyond this
SESSION_COOKIE = "reqtool_session"
REFRESH_COOKIE = "reqtool_refresh"
CSRF_HEADER = "x-reqtool-csrf"     # browser clients send it on every request; cross-site pages cannot
TOKEN_ISSUER = "reqtool"
TOKEN_AUDIENCE = "reqtool-api"


_DUMMY: Optional[tuple[str, str]] = None


def _dummy_hash() -> tuple[str, str]:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("reqtool-timing-equaliser")
    return _DUMMY


def hash_password(password: str, salt: Optional[bytes] = None, iterations: Optional[int] = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations or PBKDF2_ITERATIONS)
    return key.hex(), salt.hex()


def verify_password(password: str, password_hash: str, salt_hex: str, iterations: Optional[int] = None) -> bool:
    """Check a password against a stored hash (``iterations`` defaults to the legacy count)."""
    salt = bytes.fromhex(salt_hex)
    key, _ = hash_password(password, salt, iterations or LEGACY_ITERATIONS)
    return hmac.compare_digest(key, password_hash)


def create_token(username: str, role: str, repo_root: Path, expires_in: int = TOKEN_LIFETIME,
                 token_version: int = 0, kind: str = "access", auth_at: Optional[int] = None) -> str:
    """Sign a token. ``kind`` is ``access`` or ``refresh``; ``auth_at`` is when the password was entered."""
    import jwt
    now = int(time.time())
    return jwt.encode(
        {"sub": username, "role": role, "tv": token_version, "iat": now, "exp": now + expires_in,
         "iss": TOKEN_ISSUER, "aud": TOKEN_AUDIENCE, "typ": kind, "auth_at": auth_at or now},
        _get_secret_key(repo_root), algorithm="HS256")


def verify_token(token: str, repo_root: Path) -> Optional[dict[str, Any]]:
    """Return the claims of a valid token, else None (algorithm, expiry, issuer and audience are enforced)."""
    import jwt
    try:
        return jwt.decode(token, _get_secret_key(repo_root), algorithms=["HS256"],
                          issuer=TOKEN_ISSUER, audience=TOKEN_AUDIENCE,
                          options={"require": ["exp", "iat", "sub", "iss", "aud"]})
    except Exception:
        return None


class LoginThrottle:
    """Sliding-window limiter for failed logins, per username and per client address (in memory)."""

    def __init__(self, max_failures: int = 5, window: float = 60.0):
        self.max_failures, self.window = max_failures, window
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.window
        recent = [t for t in self._fails.get(key, []) if t > cutoff]
        if recent:
            self._fails[key] = recent
        else:
            self._fails.pop(key, None)
        return recent

    def retry_after(self, *keys: str) -> int:
        """Seconds to wait if any key is over the limit, else 0."""
        wait = 0.0
        for key in keys:
            recent = self._recent(key)
            if len(recent) >= self.max_failures:
                wait = max(wait, recent[0] + self.window - time.monotonic())
        return int(wait) + 1 if wait > 0 else 0

    MAX_KEYS = 10_000

    def record_failure(self, *keys: str) -> None:
        for key in keys:
            self._fails.setdefault(key, []).append(time.monotonic())
        if len(self._fails) > self.MAX_KEYS:
            self._prune()

    def _prune(self) -> None:
        """Bound memory: drop expired keys, then the oldest ones if still over the cap."""
        for key in list(self._fails):
            self._recent(key)
        excess = len(self._fails) - self.MAX_KEYS
        if excess > 0:
            oldest = sorted(self._fails, key=lambda k: self._fails[k][-1])[:excess]
            for key in oldest:
                self._fails.pop(key, None)

    def reset(self, *keys: str) -> None:
        for key in keys:
            self._fails.pop(key, None)


login_throttle = LoginThrottle()


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


def sign_approval_v2(uid: str, version: str, username: str, content_hash: str, repo_root: Path) -> str:
    """Approval signature that also covers the approved content.

    v1 signed only (uid, version, user), so the approved text could be edited
    afterwards without invalidating the signature. v2 includes the content hash.
    """
    secret = _get_secret_key(repo_root)
    msg = f"APPROVE2:{uid}:v{version}:{username}:{content_hash}".encode("utf-8")
    return f"SIG-v2-{hmac.new(secret, msg, hashlib.sha256).hexdigest()[:48]}"


def check_approval(req: dict[str, Any], repo_root: Path) -> str:
    """Classify a requirement's approval signature.

    Returns one of: ``none`` (no signature), ``legacy`` (v1, cannot bind content),
    ``valid``, ``stale`` (genuine signature but content changed since), ``invalid``.
    """
    app = req.get("approval") or {}
    sig = app.get("signature")
    if not sig:
        return "none"
    if str(sig).startswith("SIG-v1-"):
        return "legacy"
    signed_hash = app.get("signed_hash", "")
    expected = sign_approval_v2(
        req.get("uid", ""), str(app.get("signed_version", "")), str(app.get("approved_by", "")),
        signed_hash, repo_root)
    if not hmac.compare_digest(str(sig), expected):
        return "invalid"
    return "valid" if req.get("content_hash") == signed_hash else "stale"


class UserStore:
    def __init__(self, root: Path):
        self.root = root
        self.users_file = root / ".reqtool" / "users.yaml"

    def load_users(self) -> dict[str, dict[str, Any]]:
        """Return the user table. No account is ever created implicitly."""
        if not self.users_file.exists():
            return {}
        data = load_yaml(self.users_file) or {}
        return data.get("users", {})

    def has_users(self) -> bool:
        return bool(self.load_users())

    def has_default_credentials(self) -> bool:
        """True if a legacy ``admin`` / ``admin123`` account (seeded by v0.5.0 and earlier) exists."""
        u = self.load_users().get(LEGACY_DEFAULT_USER)
        return u is not None and verify_password(
            LEGACY_DEFAULT_PASSWORD, u.get("password_hash", ""), u.get("salt", "") or "00", u.get("iterations"))

    def save_users(self, users: dict[str, dict[str, Any]]):
        self.users_file.parent.mkdir(parents=True, exist_ok=True)
        ensure_secrets_ignored(self.root)
        save_yaml(self.users_file, {"users": users})
        _restrict(self.users_file)

    def authenticate(self, username: str, password: str) -> Optional[dict[str, Any]]:
        users = self.load_users()
        user = users.get(username)
        if not user:
            # Spend the same time as a real check so response time does not reveal valid usernames.
            h, salt = _dummy_hash()
            verify_password(password, h, salt, PBKDF2_ITERATIONS)
            return None
        if not verify_password(password, user.get("password_hash", ""), user.get("salt", ""),
                               user.get("iterations")):
            return None
        if username == LEGACY_DEFAULT_USER and password == LEGACY_DEFAULT_PASSWORD:
            # Well-known credentials from older releases: never accept them.
            log.warning("Refusing login with the legacy default admin password; reset it with `req user passwd admin`.")
            return None
        if (user.get("iterations") or LEGACY_ITERATIONS) < PBKDF2_ITERATIONS:
            # Upgrade an old hash now that we hold the plaintext.
            h, salt = hash_password(password)
            user.update(password_hash=h, salt=salt, iterations=PBKDF2_ITERATIONS)
            users[username] = user
            self.save_users(users)
        return user

    def resolve_token(self, token: Optional[str]) -> Optional[dict[str, Any]]:
        """The current user record for a valid token, or None (unknown user or revoked version)."""
        return self._resolve(token, "access")

    def resolve_refresh(self, token: Optional[str]) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
        """(user, claims) for a valid refresh token that is still within the maximum session age."""
        payload = verify_token(token, self.root) if token else None
        if not payload or payload.get("typ") != "refresh":
            return None
        if time.time() - int(payload.get("auth_at", 0)) > SESSION_MAX_AGE:
            return None
        user = self._resolve(token, "refresh")
        return (user, payload) if user else None

    def _resolve(self, token: Optional[str], kind: str) -> Optional[dict[str, Any]]:
        payload = verify_token(token, self.root) if token else None
        if not payload or payload.get("typ", "access") != kind:  # a refresh token is never an access token
            return None
        user = self.load_users().get(payload.get("sub", ""))
        if not user or payload.get("tv", 0) != user.get("token_version", 0):
            return None
        return user

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
            "iterations": PBKDF2_ITERATIONS,
            "token_version": 0,
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
            u["iterations"] = PBKDF2_ITERATIONS
            u["token_version"] = int(u.get("token_version", 0)) + 1  # revoke tokens issued before the change
        if "full_name" in updates:
            u["full_name"] = updates["full_name"]
        if "email" in updates:
            u["email"] = updates["email"]
        if "role" in updates and updates["role"] in ("admin", "editor", "viewer"):
            if u.get("role") != updates["role"]:
                u["token_version"] = int(u.get("token_version", 0)) + 1
            u["role"] = updates["role"]
        users[username] = u
        self.save_users(users)
        return u
