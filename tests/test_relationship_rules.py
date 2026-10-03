"""MOD-02: cross_layer_rules are enforced per hierarchy.enforce."""
from tests.conftest import make_req
from reqtool.validation import validate_all
from reqtool.stores.hierarchy_store import check_relationship, parse_hierarchy


def _rel(t, uid):
    return {"type": t, "target": {"uid": uid}}


def _mode(client, mode):
    client.app.state.store.hierarchy.enforce = mode


def _pair(client):
    phys = make_req(client, title="P", req_type="physical")
    story = make_req(client, title="S", req_type="story")
    return phys, story


def test_default_rules_flag_physical_satisfies_story(store):
    assert check_relationship(store.hierarchy, "physical", "story", "satisfies")
    assert check_relationship(store.hierarchy, "story", "physical", "satisfies") is None


def test_strategic_items_may_trace_to_needs_and_systems(store):
    h = store.hierarchy
    for src in ("theme", "initiative", "epic"):
        assert check_relationship(h, src, "stakeholder_need", "traces_to") is None
        assert check_relationship(h, src, "functional", "traces_to") is None


def test_generic_and_unlisted_pairs_unconstrained(store):
    h = store.hierarchy
    assert check_relationship(h, "physical", "story", "relates_to") is None
    assert check_relationship(h, "physical", "physical", "depends_on") is None


def test_error_mode_rejects_new_bad_relationship(client):
    _mode(client, "error")
    phys, story = _pair(client)
    r = client.put(f"/requirements/{phys['uid']}", json={"relationships": [_rel("satisfies", story["uid"])]})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "relationship_violation"
    r = client.post("/requirements", json={"title": "X", "req_type": "physical",
                                           "relationships": [_rel("satisfies", story["uid"])]})
    assert r.status_code == 409


def test_error_mode_allows_valid_relationship(client):
    _mode(client, "error")
    phys, story = _pair(client)
    r = client.put(f"/requirements/{story['uid']}", json={"relationships": [_rel("satisfies", phys["uid"])]})
    assert r.status_code == 200


def test_existing_bad_relationship_does_not_block_other_edits(client):
    phys, story = _pair(client)
    client.put(f"/requirements/{phys['uid']}", json={"relationships": [_rel("satisfies", story["uid"])]})
    _mode(client, "error")
    rels = client.get(f"/requirements/{phys['uid']}").json()["relationships"]
    r = client.put(f"/requirements/{phys['uid']}", json={"title": "renamed", "relationships": rels})
    assert r.status_code == 200


def test_warn_mode_writes_but_validation_warns(client):
    phys, story = _pair(client)
    assert client.put(f"/requirements/{phys['uid']}",
                      json={"relationships": [_rel("satisfies", story["uid"])]}).status_code == 200
    res = validate_all(client.app.state.store)
    assert any(w["code"] == "relationship_violation" for w in res["warnings"])


def test_error_mode_validation_error_and_off_silent(client):
    phys, story = _pair(client)
    client.put(f"/requirements/{phys['uid']}", json={"relationships": [_rel("satisfies", story["uid"])]})
    _mode(client, "error")
    assert any(e["code"] == "relationship_violation" for e in validate_all(client.app.state.store)["errors"])
    _mode(client, "off")
    res = validate_all(client.app.state.store)
    assert not any(x["code"] == "relationship_violation" for x in res["errors"] + res["warnings"])
