"""DAT-16: CSV import is validated up front, atomic, and cannot create pre-approved items."""
from tests.conftest import make_req


def _post(client, csv, **params):
    return client.post("/import/csv/upload", params=params, content=csv.encode(), headers={"content-type": "text/csv"})


def _count(client):
    return len(client.app.state.store.requirements)


def test_bad_row_leaves_repository_unchanged(client):
    csv = "id,title\nA-1,Good\nA-2,\nA-3,Also good"
    r = _post(client, csv)
    assert r.status_code == 422
    assert [e["row"] for e in r.json()["detail"]["errors"]] == [2]
    assert _count(client) == 0
    files = list((client.app.state.store.root / "requirements").glob("*.yaml"))
    assert files == []


def test_ragged_csv_is_422_not_500_and_writes_nothing(client):
    r = _post(client, "id,title,domain\nA-1,One,firmware\nA-2,Two\nA-3,Three,x,extra")
    assert r.status_code == 422
    msgs = " ".join(e["error"] for e in r.json()["detail"]["errors"])
    assert "fewer" in msgs and "more" in msgs
    assert _count(client) == 0


def test_status_column_is_downgraded_to_initial_state(client):
    r = _post(client, "id,title,status\nA-1,Sneaky,approved")
    assert r.status_code == 201
    got = client.get("/requirements/A-1").json()
    assert got["status"] == "draft"
    assert got["approval"]["status"] != "approved"


def test_keep_status_keeps_valid_states_and_rejects_invalid(client):
    assert _post(client, "id,title,status\nA-1,T,approved", keep_status="true").status_code == 201
    assert client.get("/requirements/A-1").json()["status"] == "approved"
    r = _post(client, "id,title,status\nA-2,T,nonsense", keep_status="true")
    assert r.status_code == 422 and "not a state" in r.json()["detail"]["errors"][0]["error"]


def test_keep_status_needs_admin_when_logged_in(repo_root):
    from fastapi.testclient import TestClient
    from reqtool.api import create_app
    from reqtool.auth import UserStore
    us = UserStore(repo_root)
    us.create_user("ed", "editor password", role="editor")
    us.create_user("ad", "admin password!", role="admin")
    c = TestClient(create_app(repo_root, auth_mode="required"))
    tok = lambda u, p: {"Authorization": "Bearer " + c.post("/auth/login", json={"username": u, "password": p}).json()["access_token"]}
    csv = b"id,title,status\nA-1,T,approved"
    h = {**tok("ed", "editor password"), "content-type": "text/csv"}
    assert c.post("/import/csv/upload?keep_status=true", content=csv, headers=h).status_code == 403
    h = {**tok("ad", "admin password!"), "content-type": "text/csv"}
    assert c.post("/import/csv/upload?keep_status=true", content=csv, headers=h).status_code == 201


def test_dry_run_validates_without_writing(client):
    ok = _post(client, "id,title\nA-1,One\nA-2,Two", dry_run="true")
    assert ok.status_code == 200 and ok.json()["valid"] == 2 and _count(client) == 0
    bad = _post(client, "id,title\nA-1,One\nA-1,Dup", dry_run="true")
    assert bad.status_code == 422 and _count(client) == 0


def test_duplicate_and_unsafe_ids_and_missing_parent(client):
    make_req(client, id="EXIST-1")
    r = _post(client, "id,title,parentId\nEXIST-1,x,\n../evil,y,\nB-1,z,NOPE")
    errs = {e["row"]: e["error"] for e in r.json()["detail"]["errors"]}
    assert "already exists" in errs[1] and "Invalid" in errs[2] and "parent" in errs[3]


def test_parents_resolve_within_the_file_and_to_existing_items(client):
    existing = make_req(client, id="OLD-1")
    r = _post(client, "id,title,parentId\nP,Parent,\nC,Child,P\nD,Under existing,OLD-1")
    assert r.status_code == 201 and r.json()["imported"] == 3
    assert client.get("/requirements/C").json()["parentId"] == client.get("/requirements/P").json()["uid"]
    assert client.get("/requirements/D").json()["parentId"] == existing["uid"]


def test_failure_during_apply_rolls_everything_back(client):
    client.app.state.store.hierarchy.enforce = "error"
    # a task cannot have children: passes row validation but fails when parents are applied
    r = _post(client, "id,title,type,parentId\nT-1,Task,task,\nS-1,Story,story,T-1")
    assert r.status_code == 422 and "rolled back" in r.json()["detail"]["message"]
    assert _count(client) == 0
    assert list((client.app.state.store.root / "requirements").glob("*.yaml")) == []
