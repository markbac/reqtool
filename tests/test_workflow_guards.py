"""DAT-04: bulk update, approve and clone enforce the same guards as single update."""
from tests.conftest import make_req


def _illegal_target(client, uid):
    wf = client.get("/workflow").json()
    cur = client.get(f"/requirements/{uid}").json()["status"]
    legal = set((wf.get("transitions") or {}).get(cur, []))
    for st in wf.get("states", []):
        name = st if isinstance(st, str) else st.get("id") or st.get("name")
        if name and name != cur and name not in legal:
            return name
    raise AssertionError("no illegal target in workflow")


def test_bulk_rejects_illegal_status_transition(client):
    uid = make_req(client, title="A")["uid"]
    target = _illegal_target(client, uid)
    r = client.post("/requirements/bulk", json={"uids": [uid], "fields": {"status": target}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == [] and body["failed"] == [uid]
    assert uid in body["errors"]
    assert client.get(f"/requirements/{uid}").json()["status"] != target


def test_bulk_allows_legal_transition_and_reports_missing(client):
    uid = make_req(client, title="A")["uid"]
    wf = client.get("/workflow").json()
    cur = client.get(f"/requirements/{uid}").json()["status"]
    legal = wf["transitions"][cur][0]
    r = client.post("/requirements/bulk", json={"uids": [uid, "nope"], "fields": {"status": legal}}).json()
    assert r["updated"] == [uid] and r["failed"] == ["nope"] and r["errors"]["nope"] == "not found"


def test_bulk_without_status_still_works(client):
    uid = make_req(client, title="A")["uid"]
    r = client.post("/requirements/bulk", json={"uids": [uid], "fields": {"owner": "bob"}}).json()
    assert r["updated"] == [uid] and r["errors"] == {}


def test_approve_respects_workflow_guard(client):
    uid = make_req(client, title="A")["uid"]
    cur = client.get(f"/requirements/{uid}").json()["status"]
    legal = set(client.get("/workflow").json()["transitions"].get(cur, []))
    r = client.post(f"/requirements/{uid}/approve", json={"approved_by": "alice"})
    if "approved" in legal:
        assert r.status_code == 200
    else:
        assert r.status_code == 409 and r.json()["detail"]["error"] == "workflow_guard"
        assert client.get(f"/requirements/{uid}").json()["status"] == cur


def test_mutations_blocked_while_merge_conflicts(client, monkeypatch):
    uid = make_req(client, title="A")["uid"]
    monkeypatch.setattr("reqtool.routers.requirements.has_conflicts", lambda root: True)
    assert client.post("/requirements/bulk", json={"uids": [uid], "fields": {"owner": "x"}}).status_code == 409
    assert client.post(f"/requirements/{uid}/clone").status_code == 409
    assert client.post(f"/requirements/{uid}/approve", json={"approved_by": "a"}).status_code == 409
    assert client.get(f"/requirements/{uid}").json().get("owner") != "x"


def test_approve_blocked_when_workflow_forbids_it(client, monkeypatch):
    uid = make_req(client, title="A")["uid"]
    store = client.app.state.store
    real = store.validate_transition
    monkeypatch.setattr(
        store, "validate_transition",
        lambda req, to: "Transition not permitted." if to == "approved" else real(req, to),
    )
    r = client.post(f"/requirements/{uid}/approve", json={"approved_by": "alice"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "workflow_guard"
    assert client.get(f"/requirements/{uid}").json()["status"] == "draft"
