"""MOD-11: a workflow guard can require children to be closed before the parent is."""
from tests.conftest import make_req
from reqtool.validation import validate_all


def _mode(client, mode):
    store = client.app.state.store
    for wf in store.hierarchy.workflows.values():
        if "done" in wf.guards:
            wf.guards["done"].children_enforce = mode


def _tree(client):
    ini = make_req(client, title="I", req_type="initiative")
    ep = make_req(client, title="E", req_type="epic", parentId=ini["uid"])
    return ini, ep


def _to_done(client, uid):
    # lightweight: draft -> active -> done
    client.post(f"/requirements/{uid}/transition", json={"to_state": "active"})
    return client.post(f"/requirements/{uid}/transition", json={"to_state": "done"})


def test_default_is_warn_and_does_not_block(client):
    ini, _ = _tree(client)
    r = _to_done(client, ini["uid"])
    assert r.status_code == 200, r.text
    warns = validate_all(client.app.state.store)["warnings"]
    assert any(w["code"] == "open_children" and w["uid"] == ini["uid"] for w in warns)


def test_error_mode_blocks_with_message(client):
    _mode(client, "error")
    ini, ep = _tree(client)
    r = _to_done(client, ini["uid"])
    assert r.status_code >= 400
    assert ep["id"] in r.text and "child" in r.text.lower()


def test_error_mode_allows_when_children_closed_or_cancelled(client):
    _mode(client, "error")
    ini, ep = _tree(client)
    client.app.state.store.requirements[ep["uid"]]["status"] = "cancelled"
    assert _to_done(client, ini["uid"]).status_code == 200


def test_off_mode_is_silent(client):
    _mode(client, "off")
    ini, _ = _tree(client)
    assert _to_done(client, ini["uid"]).status_code == 200
    assert not any(w["code"] == "open_children" for w in validate_all(client.app.state.store)["warnings"])


def test_invalid_mode_falls_back_to_warn():
    from reqtool.models import WorkflowGuard
    assert WorkflowGuard(children_enforce="loud").children_enforce == "warn"
