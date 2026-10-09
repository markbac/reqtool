"""UI-03: suspect links are surfaced by the tree, validation and metrics, and can be cleared."""
from tests.conftest import make_req
from reqtool.validation import validate_all


def _setup(client):
    up = make_req(client, title="Upstream")
    down = make_req(client, title="Downstream")
    client.put(f"/requirements/{down['uid']}", json={"relationships": [{"type": "derived_from", "target": {"uid": up["uid"]}}]})
    client.put(f"/requirements/{up['uid']}", json={"title": "Upstream changed"})
    return up, down


def _node(tree, uid):
    for n in tree:
        if n["uid"] == uid:
            return n
        hit = _node(n.get("children", []), uid)
        if hit:
            return hit


def test_editing_upstream_flags_dependant_in_tree(client):
    up, down = _setup(client)
    tree = client.app.state.store.build_tree()
    assert _node(tree, down["uid"])["suspect_count"] == 1
    assert _node(tree, up["uid"])["suspect_count"] == 0


def test_clear_removes_flag_and_count(client):
    up, down = _setup(client)
    assert client.post(f"/requirements/{down['uid']}/relationships/0/clear-suspect").status_code == 200
    assert _node(client.app.state.store.build_tree(), down["uid"])["suspect_count"] == 0
    assert client.get("/metrics").json()["totals"]["suspect_links"] == 0


def test_metrics_counts_suspect_links(client):
    _setup(client)
    assert client.get("/metrics").json()["totals"]["suspect_links"] == 1


def test_validation_warns_for_approved_item_with_suspect_link(client):
    up, down = _setup(client)
    store = client.app.state.store
    store.requirements[down["uid"]]["approval"] = {"status": "approved"}
    codes = [w["code"] for w in validate_all(store)["warnings"]]
    assert "suspect_link" in codes
    store.requirements[down["uid"]]["approval"] = {"status": "draft"}
    assert "suspect_link" not in [w["code"] for w in validate_all(store)["warnings"]]
