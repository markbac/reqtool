"""INT-03: assigning a requirement to an iteration changes that iteration's metrics."""
from tests.conftest import make_req


def _metrics(client, it):
    r = client.get(f"/iterations/{it}/metrics")
    assert r.status_code == 200, r.text
    return r.json()


def test_assignment_changes_totals(client):
    client.post("/iterations", json={"id": "s1", "title": "Sprint One"})
    assert _metrics(client, "s1")["total_requirements"] == 0
    a = make_req(client, title="a", iteration="s1")
    make_req(client, title="b", iteration="s1")
    make_req(client, title="c", iteration="other")
    m = _metrics(client, "s1")
    assert m["total_requirements"] == 2 and m["draft"] == 2
    client.app.state.store.requirements[a["uid"]]["status"] = "approved"
    m = _metrics(client, "s1")
    assert m["approved"] == 1 and m["completion_percentage"] == 50


def test_matches_by_title_and_ignores_deleted(client):
    client.post("/iterations", json={"id": "s2", "title": "Sprint-2"})
    r = make_req(client, title="a", iteration="Sprint-2")
    assert _metrics(client, "s2")["total_requirements"] == 1
    client.delete(f"/requirements/{r['uid']}")
    assert _metrics(client, "s2")["total_requirements"] == 0


def test_legacy_iteration_id_is_migrated_on_load(client):
    store = client.app.state.store
    r = make_req(client, title="old")
    path = store.req_path(r["uid"])
    from reqtool.fileio import load_yaml, save_yaml
    data = load_yaml(path)
    data["iteration_id"] = "s3"
    data.pop("iteration", None)
    save_yaml(path, data)
    store.load()
    loaded = store.requirements[r["uid"]]
    assert loaded["iteration"] == "s3" and "iteration_id" not in loaded
