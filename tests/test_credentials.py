"""SEC-05: credential handling -- stored work factor, rehash, throttling, JWT validation, revocation."""
import time

import jwt
from fastapi.testclient import TestClient

import reqtool.auth as auth
from reqtool.api import create_app
from reqtool.auth import UserStore, hash_password, create_token, verify_token
from reqtool.fileio import load_yaml, save_yaml


def _make_client(repo_root, auth_mode="required"):
    return TestClient(create_app(repo_root, auth_mode=auth_mode))


def _login(c, user, pw):
    return c.post("/auth/login", json={"username": user, "password": pw})


def test_new_hashes_store_the_iteration_count(repo_root):
    rec = UserStore(repo_root).create_user("amy", "correct horse", role="admin")
    assert rec["iterations"] == auth.PBKDF2_ITERATIONS


def test_real_work_factor_is_owasp_level():
    import importlib
    fresh = importlib.import_module("reqtool.auth")
    # module constants are patched to 1000 by the suite fixture; read the source default
    assert fresh.LEGACY_ITERATIONS == 100_000
    src = open(fresh.__file__).read()
    assert "PBKDF2_ITERATIONS = 600_000" in src


def test_old_hash_verifies_then_upgrades(repo_root, monkeypatch):
    monkeypatch.setattr(auth, "PBKDF2_ITERATIONS", 120_000)  # above the legacy count so an upgrade is due
    h, salt = hash_password("old password", iterations=100_000)
    save_yaml(repo_root / ".reqtool" / "users.yaml", {"users": {"bob": {
        "username": "bob", "role": "editor", "password_hash": h, "salt": salt}}})
    us = UserStore(repo_root)
    assert us.authenticate("bob", "wrong") is None
    assert us.authenticate("bob", "old password") is not None
    rec = load_yaml(repo_root / ".reqtool" / "users.yaml")["users"]["bob"]
    assert rec["iterations"] == auth.PBKDF2_ITERATIONS and rec["password_hash"] != h
    assert us.authenticate("bob", "old password") is not None  # still works after the upgrade


def test_passwords_are_not_stripped(repo_root):
    c = _make_client(repo_root)
    # bootstrap the first account from "localhost"
    r = c.post("/auth/users", json={"username": "root", "password": "  padded pass  "})
    assert r.status_code == 201, r.text
    assert _login(c, "root", "  padded pass  ").status_code == 200
    assert _login(c, "root", "padded pass").status_code == 401


def test_six_bad_logins_in_a_minute_are_throttled(repo_root):
    UserStore(repo_root).create_user("amy", "correct horse", role="admin")
    c = _make_client(repo_root)
    codes = [_login(c, "amy", "nope").status_code for _ in range(5)]
    assert codes == [401] * 5
    r = _login(c, "amy", "nope")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    # even the right password is refused while throttled
    assert _login(c, "amy", "correct horse").status_code == 429


def test_throttle_is_per_account_and_per_address(repo_root):
    us = UserStore(repo_root)
    us.create_user("amy", "correct horse", role="admin")
    us.create_user("ben", "another horse", role="editor")
    c = TestClient(create_app(repo_root, auth_mode="required"), client=("198.51.100.7", 1))
    for _ in range(5):
        assert _login(c, "amy", "x").status_code == 401
    other = TestClient(create_app(repo_root, auth_mode="required"), client=("198.51.100.8", 1))
    assert _login(other, "ben", "another horse").status_code == 200   # different account and address
    assert _login(c, "ben", "another horse").status_code == 429       # same address is limited


def test_throttle_window_expires():
    t = auth.LoginThrottle(max_failures=2, window=0.05)
    t.record_failure("k"); t.record_failure("k")
    assert t.retry_after("k") > 0
    time.sleep(0.07)
    assert t.retry_after("k") == 0


def test_success_resets_account_counter(repo_root):
    UserStore(repo_root).create_user("amy", "correct horse", role="admin")
    c = _make_client(repo_root)
    for _ in range(4):
        _login(c, "amy", "bad")
    assert _login(c, "amy", "correct horse").status_code == 200
    assert auth.login_throttle.retry_after("user:amy") == 0  # account counter cleared (the address keeps its own)
    assert _login(c, "amy", "bad").status_code == 401


def test_token_rejects_alg_none_wrong_issuer_audience_and_expiry(repo_root):
    UserStore(repo_root).create_user("amy", "correct horse", role="admin")
    good = create_token("amy", "admin", repo_root)
    assert verify_token(good, repo_root)["sub"] == "amy"
    claims = jwt.decode(good, options={"verify_signature": False})
    assert verify_token(jwt.encode(claims, key=None, algorithm="none"), repo_root) is None
    key = auth._get_secret_key(repo_root)
    assert verify_token(jwt.encode({**claims, "iss": "evil"}, key, algorithm="HS256"), repo_root) is None
    assert verify_token(jwt.encode({**claims, "aud": "other"}, key, algorithm="HS256"), repo_root) is None
    assert verify_token(jwt.encode({**claims, "exp": int(time.time()) - 5}, key, algorithm="HS256"), repo_root) is None
    assert verify_token(jwt.encode(claims, b"x" * 32, algorithm="HS256"), repo_root) is None


def test_default_lifetime_is_hours(repo_root):
    claims = verify_token(create_token("amy", "admin", repo_root), repo_root)
    assert claims["exp"] - claims["iat"] == 12 * 3600


def test_password_change_revokes_existing_tokens(repo_root):
    us = UserStore(repo_root)
    us.create_user("amy", "correct horse", role="admin")
    c = _make_client(repo_root)
    tok = _login(c, "amy", "correct horse").json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert c.get("/requirements", headers=h).status_code == 200
    us.update_user("amy", {"password": "a new password"})
    assert c.get("/requirements", headers=h).status_code == 401
    tok2 = _login(c, "amy", "a new password").json()["access_token"]
    assert c.get("/requirements", headers={"Authorization": f"Bearer {tok2}"}).status_code == 200


def test_role_change_revokes_tokens(repo_root):
    us = UserStore(repo_root)
    us.create_user("amy", "correct horse", role="admin")
    c = _make_client(repo_root)
    tok = _login(c, "amy", "correct horse").json()["access_token"]
    us.update_user("amy", {"role": "viewer"})
    assert c.get("/requirements", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
