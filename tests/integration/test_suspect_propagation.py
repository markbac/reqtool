"""DAT-08: suspect flags propagate transitively, are audited, and do not corrupt hashes."""
from tests.conftest import make_req
from reqtool.validation import validate_all


def _chain(client):
    a = make_req(client, title="A")
    b = make_req(client, title="B", relationships=[{"type": "derived_from", "target": {"uid": a["uid"]}}])
    c = make_req(client, title="C", relationships=[{"type": "derived_from", "target": {"uid": b["uid"]}}])
    return a, b, c


def _get(client, uid):
    return client.get(f"/requirements/{uid}").json()


def test_change_flags_b_and_transitively_c_with_history(client):
    a, b, c = _chain(client)
    client.put(f"/requirements/{a['uid']}", json={"title": "A2"})
    for uid, upstream in ((b["uid"], a), (c["uid"], b)):
        got = _get(client, uid)
        assert got["relationships"][0]["suspect"] is True
        assert any("became suspect" in h["summary"] and upstream["id"] in h["summary"] for h in got["history"])
    assert not _get(client, a["uid"]).get("relationships")


def test_no_version_bump_and_no_hash_mismatch(client):
    a, b, c = _chain(client)
    v = _get(client, b["uid"])["version"]
    client.put(f"/requirements/{a['uid']}", json={"title": "A2"})
    assert _get(client, b["uid"])["version"] == v
    errs = [e for e in validate_all(client.app.state.store)["errors"] if e["code"] == "hash_mismatch"]
    assert errs == []


def test_second_change_does_not_duplicate_history(client):
    a, b, c = _chain(client)
    client.put(f"/requirements/{a['uid']}", json={"title": "A2"})
    client.put(f"/requirements/{a['uid']}", json={"title": "A3"})
    n = [h for h in _get(client, b["uid"])["history"] if "became suspect" in h["summary"]]
    assert len(n) == 1


def test_cleared_link_is_flagged_again_by_a_new_change(client):
    a, b, c = _chain(client)
    client.put(f"/requirements/{a['uid']}", json={"title": "A2"})
    client.post(f"/requirements/{b['uid']}/relationships/0/clear-suspect")
    client.put(f"/requirements/{a['uid']}", json={"title": "A3"})
    assert _get(client, b["uid"])["relationships"][0]["suspect"] is True


def test_cycles_terminate(client):
    a, b, c = _chain(client)
    client.put(f"/requirements/{a['uid']}", json={"relationships": [{"type": "relates_to", "target": {"uid": c["uid"]}}]})
    client.put(f"/requirements/{b['uid']}", json={"title": "B2"})  # B -> C -> A -> B loop
    assert _get(client, a["uid"])["relationships"][0].get("suspect") is True


def test_hash_ignores_suspect_flag():
    from reqtool.fileio import compute_requirement_hash
    base = {"id": "X", "relationships": [{"type": "derived_from", "target": {"uid": "u"}}]}
    flagged = {"id": "X", "relationships": [{"type": "derived_from", "target": {"uid": "u"}, "suspect": True}]}
    assert compute_requirement_hash(base) == compute_requirement_hash(flagged)
    other = {"id": "X", "relationships": [{"type": "depends_on", "target": {"uid": "u"}}]}
    assert compute_requirement_hash(base) != compute_requirement_hash(other)
