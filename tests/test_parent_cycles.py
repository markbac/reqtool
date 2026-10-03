"""MOD-03: parentId cycles are rejected on write and tolerated in existing data."""
from tests.conftest import make_req
from reqtool.validation import validate_all


def _chain(client):
    a = make_req(client, title="A")
    b = make_req(client, title="B", parentId=a["uid"])
    c = make_req(client, title="C", parentId=b["uid"])
    return a, b, c


def test_self_parent_rejected(client):
    a = make_req(client, title="A")
    r = client.put(f"/requirements/{a['uid']}", json={"parentId": a["uid"]})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "parent_cycle"


def test_descendant_as_parent_rejected(client):
    a, b, c = _chain(client)
    r = client.put(f"/requirements/{a['uid']}", json={"parentId": c["uid"]})
    assert r.status_code == 409
    assert client.get(f"/requirements/{a['uid']}").json().get("parentId") in (None, "")


def test_valid_reparent_allowed(client):
    a, b, c = _chain(client)
    r = client.put(f"/requirements/{c['uid']}", json={"parentId": a["uid"]})
    assert r.status_code == 200


def test_bulk_reports_cycle_per_item(client):
    a, b, c = _chain(client)
    r = client.post("/requirements/bulk", json={"uids": [a["uid"]], "fields": {"parentId": c["uid"]}})
    assert r.status_code == 200
    body = r.json()
    assert body["failed"] == [a["uid"]] and "cycle" in body["errors"][a["uid"]]


def _make_cycle(store, a, b):
    store.requirements[a]["parentId"] = b
    store.requirements[b]["parentId"] = a


def test_existing_cycle_reported_and_tree_terminates(store):
    a = store.create_requirement({"title": "A"})
    b = store.create_requirement({"title": "B", "parentId": a["uid"]})
    _make_cycle(store, a["uid"], b["uid"])
    errs = [e for e in validate_all(store)["errors"] if e["code"] == "parent_cycle"]
    tree = store.build_tree()  # must not recurse forever
    assert isinstance(tree, list)
    assert errs, "cycle should be reported"
