"""SEC-19: browser sessions use HttpOnly cookies, a CSRF header and refresh tokens."""

import pytest
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.auth import (CSRF_HEADER, REFRESH_COOKIE, SESSION_COOKIE, UserStore, create_token)

PW = "correct-horse-battery"
CSRF = {CSRF_HEADER: "1"}


@pytest.fixture
def client(repo_root):
    UserStore(repo_root).create_user("root", PW, role="admin")
    return TestClient(create_app(repo_root, auth_mode="required"))


def _login(c):
    r = c.post("/auth/login", json={"username": "root", "password": PW})
    assert r.status_code == 200
    return r


def test_login_sets_httponly_strict_cookies(client):
    r = _login(client)
    cookies = r.headers.get_list("set-cookie")
    session = next(h for h in cookies if h.startswith(SESSION_COOKIE))
    refresh = next(h for h in cookies if h.startswith(REFRESH_COOKIE))
    for h in (session, refresh):
        assert "HttpOnly" in h and "SameSite=strict" in h
    assert "Path=/auth" in refresh
    assert "Secure" not in session  # plain http in tests
    assert r.json()["access_token"]  # scripts still get a bearer token


def test_secure_flag_follows_https(client):
    r = client.post("/auth/login", json={"username": "root", "password": PW}, headers={"X-Forwarded-Proto": "https"})
    assert all("Secure" in h for h in r.headers.get_list("set-cookie"))


def test_cookie_authenticates_reads(client):
    _login(client)
    assert client.get("/auth/me").json()["username"] == "root"


def test_cookie_writes_need_csrf_header(client):
    _login(client)
    body = {"title": "x", "type": "requirement"}
    r = client.post("/requirements", json=body)
    assert r.status_code == 403 and r.json()["detail"]["error"] == "csrf"
    assert client.post("/requirements", json=body, headers=CSRF).status_code != 403


def test_bearer_writes_need_no_csrf_header(client):
    tok = _login(client).json()["access_token"]
    client.cookies.clear()
    r = client.post("/requirements", json={"title": "x", "type": "requirement"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code != 403


def test_refresh_requires_csrf_header_and_rotates(client):
    _login(client)
    assert client.post("/auth/refresh").status_code == 403
    r = client.post("/auth/refresh", headers=CSRF)
    assert r.status_code == 200
    assert any(h.startswith(SESSION_COOKIE) for h in r.headers.get_list("set-cookie"))
    assert client.get("/auth/me").status_code == 200


def test_refresh_without_cookie_is_401(client):
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_access_token_cannot_be_used_as_refresh(client, repo_root):
    tok = create_token("root", "admin", repo_root)
    client.cookies.set(REFRESH_COOKIE, tok, path="/auth")
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_refresh_token_cannot_authenticate_requests(client, repo_root):
    tok = create_token("root", "admin", repo_root, kind="refresh")
    client.cookies.set(SESSION_COOKIE, tok)
    assert client.get("/auth/me").status_code == 401


def test_refresh_stops_after_max_age(client, repo_root, monkeypatch):
    import reqtool.auth as a
    _login(client)
    monkeypatch.setattr(a, "SESSION_MAX_AGE", -1)
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_password_change_revokes_refresh(client, repo_root):
    _login(client)
    UserStore(repo_root).update_user("root", {"password": "another-long-password"})
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_logout_clears_cookies(client):
    _login(client)
    assert client.post("/auth/logout").status_code == 403
    r = client.post("/auth/logout", headers=CSRF)
    assert r.status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_websocket_cookie_refused_cross_origin(client):
    _login(client)
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"Origin": "http://evil.example"}):
            pass
