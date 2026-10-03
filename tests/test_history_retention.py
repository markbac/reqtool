"""DAT-09: change history is an audit trail and must never be truncated."""
from tests.conftest import make_req


def test_requirement_history_not_truncated(client):
    uid = make_req(client)["uid"]
    for i in range(30):
        r = client.put(f"/requirements/{uid}", json={"title": f"v{i}"})
        assert r.status_code == 200, r.text
    entries = client.get(f"/requirements/{uid}/history").json()["in_file"]
    assert len(entries) >= 31
    assert entries[0]["summary"] != entries[-1]["summary"]


