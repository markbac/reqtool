"""Roles in 'required' mode: viewers read, editors add and change data, administrators do the rest."""
import pytest
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.auth import UserStore

PW = "correct-horse-battery"


@pytest.fixture
def secured(repo_root):
    users = UserStore(repo_root)
    for name, role in (("root", "admin"), ("ed", "editor"), ("vw", "viewer")):
        users.create_user(name, PW, role=role)
    return TestClient(create_app(repo_root, auth_mode="required"))


def _h(c, name):
    t = c.post("/auth/login", json={"username": name, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


# (method, path, body, lowest role allowed)
MATRIX = [
    ("GET", "/requirements", None, "viewer"),
    ("GET", "/workflows", None, "viewer"),
    ("GET", "/lint/config", None, "viewer"),
    ("POST", "/lint/text", {"text": "hello"}, "viewer"),
    ("POST", "/requirements", {"title": "x"}, "editor"),
    ("PUT", "/lint/config", {"enabled": True}, "admin"),
    ("POST", "/workflows", {"id": "wf_a", "copy_from": "formal"}, "admin"),
    ("PUT", "/hierarchy/types/functional/workflow", {"workflow": "formal"}, "admin"),
    ("DELETE", "/workflows/lightweight", None, "admin"),
    ("POST", "/repo/init", {"path": "/tmp/never-created-by-test"}, "admin"),
    ("PUT", "/config", {"repo_title": "t"}, "admin"),
]
RANK = {"viewer": 0, "editor": 1, "admin": 2}


@pytest.mark.parametrize("method,path,body,lowest", MATRIX)
@pytest.mark.parametrize("role,user", [("viewer", "vw"), ("editor", "ed"), ("admin", "root")])
def test_role_matrix(secured, method, path, body, lowest, role, user):
    r = secured.request(method, path, json=body, headers=_h(secured, user))
    if RANK[role] < RANK[lowest]:
        assert r.status_code == 403, (role, method, path, r.status_code)
    else:
        assert r.status_code != 403, (role, method, path, r.text)


def test_only_admin_deletes_items(secured):
    uid = secured.post("/requirements", json={"title": "x"}, headers=_h(secured, "ed")).json()["uid"]
    assert secured.delete(f"/requirements/{uid}", headers=_h(secured, "ed")).status_code == 403
    assert secured.delete(f"/requirements/{uid}", headers=_h(secured, "vw")).status_code == 403
    assert secured.delete(f"/requirements/{uid}", headers=_h(secured, "root")).status_code == 200


def test_editor_can_change_status_and_content(secured):
    h = _h(secured, "ed")
    uid = secured.post("/requirements", json={"title": "x"}, headers=h).json()["uid"]
    assert secured.put(f"/requirements/{uid}", json={"status": "in_review"}, headers=h).status_code == 200
    assert secured.get(f"/requirements/{uid}/transitions", headers=_h(secured, "vw")).status_code == 200


@pytest.mark.parametrize("user,role", [("vw", "viewer"), ("ed", "editor"), ("root", "admin")])
def test_permissions_endpoint(secured, user, role):
    body = secured.get("/permissions", headers=_h(secured, user)).json()
    assert body["mode"] == "required" and body["role"] == role and body["username"] == user
    perms = set(body["permissions"])
    assert "read" in perms
    assert ("write" in perms) is (role != "viewer")
    for action in ("delete", "manage_workflow", "manage_lint", "manage_repo", "manage_config"):
        assert (action in perms) is (role == "admin"), action


def test_local_mode_is_admin(client):
    body = client.get("/permissions").json()
    assert body["mode"] == "local" and body["role"] == "admin"
    assert {"read", "write", "delete", "manage_workflow", "manage_lint"} <= set(body["permissions"])
