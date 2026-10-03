"""EVT-01: server events and client relays must actually reach WebSocket clients."""
import json

from tests.conftest import make_req


def test_server_event_reaches_client_from_sync_handler(client):
    with client.websocket_connect("/ws") as ws:
        uid = make_req(client)["uid"]
        r = client.put(f"/requirements/{uid}", json={"title": "changed"})
        assert r.status_code == 200
        # a transition fires status_changed from a sync handler thread
        st = client.get(f"/requirements/{uid}").json()["status"]
        trans = client.get("/workflow").json().get("transitions", {}).get(st) or []
        assert trans, "workflow should offer a transition"
        r = client.post(f"/requirements/{uid}/transition", json={"to_state": trans[0]})
        assert r.status_code == 200, r.text
        # one event per mutation, in order (EVT-02): create, edit, then the transition
        msgs = [json.loads(ws.receive_text()) for _ in range(3)]
        assert [m["event"] for m in msgs] == ["requirement_created", "requirement_updated", "status_changed"]
        assert all(m["uid"] == uid for m in msgs)


def test_client_relay_is_broadcast(client):
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.send_text(json.dumps({"type": "PRESENCE", "payload": {"user": "alice"}}))
        got = json.loads(b.receive_text())
        assert got == {"event": "PRESENCE", "payload": {"user": "alice"}}


def test_no_clients_is_a_noop():
    from reqtool.routers.deps import broadcast_sync
    broadcast_sync("x", {"uid": "u"})  # must not raise
