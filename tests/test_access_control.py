"""SEC-01: authentication is enforced in 'required' mode; 'local' mode serves loopback only."""
from tests.conftest import review_first
import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.auth import UserStore
from reqtool.cli import cli

PW = "correct-horse-battery"


@pytest.fixture
def secured(repo_root):
    us = UserStore(repo_root)
    us.create_user("root", PW, role="admin")
    us.create_user("ed", PW, role="editor")
    us.create_user("vw", PW, role="viewer")
    return TestClient(create_app(repo_root, auth_mode="required"))


def _h(c, name):
    t = c.post("/auth/login", json={"username": name, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


# --- required mode -----------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/requirements"), ("GET", "/config"), ("GET", "/webhooks"), ("GET", "/products"),
    ("POST", "/requirements"), ("PUT", "/config"), ("POST", "/repo/init"), ("GET", "/export/audit-package"),
    ("GET", "/auth/me"), ("GET", "/auth/users"), ("GET", "/git/status"), ("POST", "/render/markdown"),
])
def test_anonymous_gets_401(secured, method, path):
    r = secured.request(method, path, json={} if method != "GET" else None)
    assert r.status_code == 401, (method, path, r.status_code)
    assert r.headers.get("www-authenticate") == "Bearer"


def test_public_endpoints_stay_open(secured):
    assert secured.get("/health").status_code == 200
    assert secured.get("/version").status_code == 200
    assert secured.post("/auth/login", json={"username": "x", "password": "y"}).status_code == 401  # reaches handler


def test_bad_and_forged_tokens_rejected(secured):
    for tok in ("garbage", "a.b.c", ""):
        assert secured.get("/requirements", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    good = _h(secured, "root")["Authorization"].split()[1]
    head, payload, sig = good.split(".")
    assert secured.get("/requirements", headers={"Authorization": f"Bearer {head}.{payload}.{sig[:-2]}xx"}).status_code == 401


def test_valid_token_works_via_header_apikey_and_query(secured):
    h = _h(secured, "root")
    tok = h["Authorization"].split()[1]
    assert secured.get("/requirements", headers=h).status_code == 200
    assert secured.get("/requirements", headers={"X-API-Key": tok}).status_code == 200
    assert secured.get(f"/requirements?access_token={tok}").status_code == 200
    # query-string tokens are for GET downloads only (drop the session cookie login set)
    secured.cookies.clear()
    assert secured.post(f"/requirements?access_token={tok}", json={"title": "x"}).status_code == 401


def test_viewer_is_read_only(secured):
    h = _h(secured, "vw")
    assert secured.get("/requirements", headers=h).status_code == 200
    r = secured.post("/requirements", json={"title": "x"}, headers=h)
    assert r.status_code == 403


def test_editor_can_write_but_not_administer(secured):
    h = _h(secured, "ed")
    assert secured.post("/requirements", json={"title": "x"}, headers=h).status_code == 201
    assert secured.put("/config", json={"repo_title": "t"}, headers=h).status_code == 403
    assert secured.post("/repo/init", json={"path": "/tmp/zzz"}, headers=h).status_code == 403
    assert secured.post("/webhooks", json={"url": "https://x.example"}, headers=h).status_code == 403
    assert secured.post("/auth/users", json={"username": "n", "password": PW}, headers=h).status_code == 403


def test_admin_can_administer(secured):
    h = _h(secured, "root")
    assert secured.put("/config", json={"repo_title": "t"}, headers=h).status_code == 200


def test_deleted_user_token_stops_working(secured, repo_root):
    h = _h(secured, "ed")
    assert secured.get("/requirements", headers=h).status_code == 200
    us = UserStore(repo_root)
    users = us.load_users()
    users.pop("ed")
    us.save_users(users)
    assert secured.get("/requirements", headers=h).status_code == 401


def test_approval_identity_is_the_token_user(secured):
    h = _h(secured, "ed")
    uid = secured.post("/requirements", json={"title": "x"}, headers=h).json()["uid"]
    review_first(secured, uid, headers=h)
    r = secured.post(f"/requirements/{uid}/approve", json={"approved_by": "ed"}, headers=h)
    assert r.status_code == 200 and r.json()["approval"]["identity_verified"] is True


def test_bootstrap_first_admin_without_token(repo_root):
    c = TestClient(create_app(repo_root, auth_mode="required"))
    r = c.post("/auth/users", json={"username": "first", "password": PW})
    assert r.status_code == 201 and r.json()["role"] == "admin"
    # now closed
    assert c.post("/auth/users", json={"username": "second", "password": PW}).status_code == 401


def test_cors_headers_on_denials(secured):
    r = secured.get("/requirements", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_websocket_requires_token(secured):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with secured.websocket_connect("/ws"):
            pass
    tok = _h(secured, "root")["Authorization"].split()[1]
    with secured.websocket_connect(f"/ws?token={tok}") as ws:
        ws.send_text(json.dumps({"type": "PRESENCE", "payload": {"u": 1}}))
        assert json.loads(ws.receive_text())["event"] == "PRESENCE"


# --- local mode --------------------------------------------------------------

def test_local_mode_serves_loopback_only(repo_root):
    remote = TestClient(create_app(repo_root, auth_mode="local"), client=("203.0.113.9", 5555))
    assert remote.get("/requirements").status_code == 403
    assert remote.post("/requirements", json={"title": "x"}).status_code == 403
    assert remote.get("/health").status_code == 200  # liveness only
    local = TestClient(create_app(repo_root, auth_mode="local"), client=("127.0.0.1", 5555))
    assert local.get("/requirements").status_code == 200


def test_local_mode_is_the_default(repo_root, monkeypatch):
    monkeypatch.delenv("REQTOOL_AUTH", raising=False)
    assert create_app(repo_root).state.auth_mode == "local"
    monkeypatch.setenv("REQTOOL_AUTH", "required")
    assert create_app(repo_root).state.auth_mode == "required"


def test_invalid_mode_rejected(repo_root):
    with pytest.raises(ValueError):
        create_app(repo_root, auth_mode="open")


def test_websocket_local_mode_rejects_remote(repo_root):
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(create_app(repo_root, auth_mode="local"), client=("203.0.113.9", 5555))
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws"):
            pass


# --- serve command -----------------------------------------------------------

def test_serve_refuses_open_network_bind_without_auth(repo_root, monkeypatch):
    monkeypatch.delenv("REQTOOL_REPO", raising=False)
    monkeypatch.delenv("REQTOOL_AUTH", raising=False)
    out = CliRunner().invoke(cli, ["serve", "--repo", str(repo_root), "--host", "0.0.0.0", "--auth", "local"])
    assert out.exit_code != 0
    assert "Refusing to listen" in out.output
    out = CliRunner().invoke(cli, ["serve", "--repo", str(repo_root), "--host", "0.0.0.0"])
    assert out.exit_code != 0 and "Refusing to listen" in out.output
    import os
    assert "REQTOOL_REPO" not in os.environ and "REQTOOL_AUTH" not in os.environ  # a refused start changes nothing
