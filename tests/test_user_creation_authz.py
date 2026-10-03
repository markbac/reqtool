"""SEC-02: only an authenticated admin may create users (plus first-user bootstrap)."""
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.auth import UserStore

PW = "correct-horse-battery"


def _login(client, user, pw=PW):
    r = client.post("/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_bootstrap_first_user_is_admin_even_if_role_requested_is_lower(client):
    r = client.post("/auth/users", json={"username": "first", "password": PW, "role": "viewer"})
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "admin"


def test_bootstrap_not_allowed_from_remote(repo_root):
    c = TestClient(create_app(repo_root), client=("203.0.113.9", 4444))
    r = c.post("/auth/users", json={"username": "evil", "password": PW})
    assert r.status_code == 403
    assert UserStore(repo_root).load_users() == {}


def test_anonymous_cannot_create_once_a_user_exists(client, repo_root):
    UserStore(repo_root).create_user("root", PW, role="admin")
    r = client.post("/auth/users", json={"username": "mallory", "password": PW, "role": "admin"})
    assert r.status_code == 401
    assert "mallory" not in UserStore(repo_root).load_users()


def test_non_admin_cannot_create(client, repo_root):
    us = UserStore(repo_root)
    us.create_user("root", PW, role="admin")
    us.create_user("ed", PW, role="editor")
    us.create_user("vw", PW, role="viewer")
    for name in ("ed", "vw"):
        r = client.post("/auth/users", json={"username": "x" + name, "password": PW}, headers=_login(client, name))
        assert r.status_code == 403, name
    assert set(UserStore(repo_root).load_users()) == {"root", "ed", "vw"}


def test_admin_can_create_with_role(client, repo_root):
    UserStore(repo_root).create_user("root", PW, role="admin")
    h = _login(client, "root")
    r = client.post("/auth/users", json={"username": "bob", "password": PW, "role": "viewer"}, headers=h)
    assert r.status_code == 201 and r.json()["role"] == "viewer"
    assert client.post("/auth/users", json={"username": "bob", "password": PW}, headers=h).status_code == 409


def test_input_validation(client, repo_root):
    UserStore(repo_root).create_user("root", PW, role="admin")
    h = _login(client, "root")
    assert client.post("/auth/users", json={"username": "a", "password": "short"}, headers=h).status_code == 422
    assert client.post("/auth/users", json={"username": "../x", "password": PW}, headers=h).status_code == 422
    assert client.post("/auth/users", json={"username": "ok", "password": PW, "role": "root"}, headers=h).status_code == 422


def test_user_listing_requires_login(client, repo_root):
    UserStore(repo_root).create_user("root", PW, role="admin")
    assert client.get("/auth/users").status_code == 401
    assert client.get("/auth/users", headers=_login(client, "root")).status_code == 200
