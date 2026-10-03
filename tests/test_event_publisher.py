"""EVT-02: every requirement mutation publishes exactly one catalogue event."""
import pytest
from tests.conftest import make_req
from reqtool import events
from reqtool.events import CATALOGUE, EventPublisher, subscription_matches, wire_name


@pytest.fixture
def captured(monkeypatch):
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(events.publisher, "_subscribers", [lambda store, ev, payload: seen.append((ev, payload))])
    return seen


def _names(seen):
    return [e for e, _ in seen]


def test_create_update_delete_emit_one_event_each(client, captured):
    r = make_req(client, title="A")
    assert _names(captured) == ["requirement_created"]
    captured.clear()
    client.put(f"/requirements/{r['uid']}", json={"title": "B"})
    assert _names(captured) == ["requirement_updated"]
    captured.clear()
    client.delete(f"/requirements/{r['uid']}")
    assert _names(captured) == ["requirement_deleted"]


def test_status_change_by_put_and_transition_emit_status_changed_once(client, captured):
    r = make_req(client, title="A", req_type="story")
    captured.clear()
    assert client.put(f"/requirements/{r['uid']}", json={"status": "ready"}).status_code == 200
    assert _names(captured) == ["status_changed"]
    captured.clear()
    assert client.post(f"/requirements/{r['uid']}/transition", json={"to_state": "in_progress"}).status_code == 200
    assert _names(captured) == ["status_changed"]
    assert captured[0][1]["from"] == "ready" and captured[0][1]["to"] == "in_progress"


def test_clone_ac_and_bulk(client, captured):
    r = make_req(client, title="A")
    captured.clear()
    client.post(f"/requirements/{r['uid']}/clone")
    assert _names(captured) == ["requirement_created"]
    captured.clear()
    ac = client.post(f"/requirements/{r['uid']}/ac", json={"text": "x"}).json()
    assert _names(captured) == ["requirement_updated"]
    captured.clear()
    ac_uid = ac["acceptance_criteria"][0]["uid"]
    client.put(f"/requirements/{r['uid']}/ac/{ac_uid}", json={"text": "y"})
    client.delete(f"/requirements/{r['uid']}/ac/{ac_uid}")
    assert _names(captured) == ["requirement_updated", "requirement_updated"]
    captured.clear()
    other = make_req(client, title="B")
    captured.clear()
    client.post("/requirements/bulk", json={"uids": [r["uid"], other["uid"]], "fields": {"priority": "high"}})
    assert _names(captured) == ["requirement_updated", "requirement_updated"]


def test_failed_writes_emit_nothing(client, captured):
    r = make_req(client, title="A", req_type="story")
    captured.clear()
    assert client.put(f"/requirements/{r['uid']}", json={"status": "done"}).status_code == 409
    assert client.put("/requirements/nope", json={"title": "x"}).status_code == 404
    assert captured == []


def test_comment_and_approve_names(client, captured):
    r = make_req(client, title="A")
    captured.clear()
    client.post(f"/artefacts/{r['uid']}/comments", json={"text": "hi", "author": "me"})
    assert _names(captured) == ["comment_added"]


def test_catalogue_and_aliases():
    assert wire_name("requirement_approved") == "approved"
    assert wire_name("status_changed") == "status_changed"
    assert subscription_matches(["approved"], "requirement_approved")
    assert subscription_matches(["requirement_approved"], "requirement_approved")
    assert not subscription_matches(["status_changed"], "requirement_created")
    assert {"requirement_created", "requirement_updated", "requirement_deleted"} <= set(CATALOGUE)


def test_unknown_event_and_failing_subscriber_isolated():
    p = EventPublisher()
    got = []
    p.subscribe(lambda s, e, pl: (_ for _ in ()).throw(RuntimeError("boom")))
    p.subscribe(lambda s, e, pl: got.append(e))
    p.publish(None, "status_changed", {})
    assert got == ["status_changed"]
    with pytest.raises(ValueError):
        p.publish(None, "made_up", {})
