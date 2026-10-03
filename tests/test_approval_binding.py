"""SEC-08: approvals are bound to the logged-in user and to the approved content."""
from reqtool.auth import UserStore, check_approval
from reqtool.validation import validate_all
from tests.conftest import make_req

PW = "correct-horse-battery"


def _login(client, name):
    t = client.post("/auth/login", json={"username": name, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_authenticated_approval_uses_login_identity(client, repo_root):
    UserStore(repo_root).create_user("alice", PW, role="editor")
    uid = make_req(client, title="A")["uid"]
    r = client.post(f"/requirements/{uid}/approve", json={"approved_by": "alice"}, headers=_login(client, "alice"))
    assert r.status_code == 200, r.text
    a = r.json()["approval"]
    assert a["approved_by"] == "alice" and a["identity_verified"] is True
    assert a["signature"].startswith("SIG-v2-")


def test_cannot_approve_as_someone_else(client, repo_root):
    UserStore(repo_root).create_user("alice", PW, role="editor")
    uid = make_req(client, title="A")["uid"]
    r = client.post(f"/requirements/{uid}/approve", json={"approved_by": "the_cto"}, headers=_login(client, "alice"))
    assert r.status_code == 403
    assert client.get(f"/requirements/{uid}").json()["status"] != "approved"


def test_viewer_cannot_approve(client, repo_root):
    UserStore(repo_root).create_user("vic", PW, role="viewer")
    uid = make_req(client, title="A")["uid"]
    r = client.post(f"/requirements/{uid}/approve", json={"approved_by": "vic"}, headers=_login(client, "vic"))
    assert r.status_code == 403


def test_local_mode_records_unverified_identity(client):
    uid = make_req(client, title="A")["uid"]
    r = client.post(f"/requirements/{uid}/approve", json={"approved_by": "bob"})
    assert r.status_code == 200
    assert r.json()["approval"]["identity_verified"] is False


def test_signature_covers_content(client, repo_root):
    uid = make_req(client, title="Original")["uid"]
    store = client.app.state.store
    r = client.post(f"/requirements/{uid}/approve", json={"approved_by": "bob"}).json()
    assert check_approval(store.requirements[uid], repo_root) == "valid"

    # edit the approved text: signature is still genuine but stale
    client.put(f"/requirements/{uid}", json={"title": "Changed after approval"})
    assert check_approval(store.requirements[uid], repo_root) == "stale"
    res = validate_all(store)
    assert any(w["code"] == "approval_stale" and w["uid"] == uid for w in res["warnings"])


def test_tampered_record_is_invalid(client, repo_root):
    uid = make_req(client, title="T")["uid"]
    store = client.app.state.store
    client.post(f"/requirements/{uid}/approve", json={"approved_by": "bob"})
    store.requirements[uid]["approval"]["approved_by"] = "someone_else"
    assert check_approval(store.requirements[uid], repo_root) == "invalid"
    assert any(e["code"] == "approval_signature_invalid" for e in validate_all(store)["errors"])


def test_legacy_v1_signature_is_reported(client, repo_root):
    uid = make_req(client, title="L")["uid"]
    store = client.app.state.store
    store.requirements[uid]["approval"] = {"status": "approved", "approved_by": "x", "signature": "SIG-v1-" + "a" * 32}
    assert check_approval(store.requirements[uid], repo_root) == "legacy"
