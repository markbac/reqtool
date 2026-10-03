"""MOD-01: allowed_children is enforced according to hierarchy.enforce."""
from tests.conftest import make_req
from reqtool.validation import validate_all


def _set_mode(client, mode):
    client.app.state.store.hierarchy.enforce = mode


def test_default_mode_is_warn(store):
    assert store.hierarchy.enforce == "warn"


def test_error_mode_rejects_bad_child_on_create(client):
    _set_mode(client, "error")
    task = make_req(client, title="T", req_type="task")
    r = client.post("/requirements", json={"title": "S", "req_type": "story", "parentId": task["uid"]})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "hierarchy_violation"


def test_error_mode_allows_valid_child(client):
    _set_mode(client, "error")
    epic = make_req(client, title="E", req_type="epic")
    r = client.post("/requirements", json={"title": "S", "req_type": "story", "parentId": epic["uid"]})
    assert r.status_code == 201


def test_error_mode_rejects_reparent_and_type_change(client):
    _set_mode(client, "error")
    epic = make_req(client, title="E", req_type="epic")
    task = make_req(client, title="T", req_type="task")
    story = make_req(client, title="S", req_type="story", parentId=epic["uid"])
    assert client.put(f"/requirements/{story['uid']}", json={"parentId": task["uid"]}).status_code == 409
    # changing the type to something the epic does not allow is also refused
    assert client.put(f"/requirements/{story['uid']}", json={"req_type": "theme"}).status_code == 409


def test_bulk_reports_violation_per_item(client):
    _set_mode(client, "error")
    task = make_req(client, title="T", req_type="task")
    story = make_req(client, title="S", req_type="story")
    r = client.post("/requirements/bulk", json={"uids": [story["uid"]], "fields": {"parentId": task["uid"]}})
    assert r.json()["failed"] == [story["uid"]]


def test_warn_mode_allows_write_but_validation_warns(client):
    task = make_req(client, title="T", req_type="task")
    r = client.post("/requirements", json={"title": "S", "req_type": "story", "parentId": task["uid"]})
    assert r.status_code == 201
    result = validate_all(client.app.state.store)
    assert any(w["code"] == "hierarchy_violation" for w in result["warnings"])
    assert not any(e["code"] == "hierarchy_violation" for e in result["errors"])


def test_error_mode_validation_reports_errors(client):
    task = make_req(client, title="T", req_type="task")
    make_req(client, title="S", req_type="story", parentId=task["uid"])
    _set_mode(client, "error")
    assert any(e["code"] == "hierarchy_violation" for e in validate_all(client.app.state.store)["errors"])


def test_off_mode_is_silent(client):
    task = make_req(client, title="T", req_type="task")
    make_req(client, title="S", req_type="story", parentId=task["uid"])
    _set_mode(client, "off")
    result = validate_all(client.app.state.store)
    assert not any(x["code"] == "hierarchy_violation" for x in result["errors"] + result["warnings"])


def test_enforce_parsed_from_yaml_and_bad_value_falls_back():
    from reqtool.stores.hierarchy_store import parse_hierarchy
    assert parse_hierarchy({"enforce": "ERROR"}).enforce == "error"
    assert parse_hierarchy({"enforce": "banana"}).enforce == "warn"
