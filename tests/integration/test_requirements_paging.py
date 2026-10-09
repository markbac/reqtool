"""PERF-06: GET /requirements can be paged and always reports the total."""
from tests.conftest import make_req


def _fill(client, n):
    store = client.app.state.store
    for i in range(n):
        uid = f"u{i:05d}"
        store.requirements[uid] = {"uid": uid, "id": f"FR-{i:05d}", "title": f"t{i}", "status": "draft"}


def test_limit_and_offset_with_total_header(client):
    _fill(client, 10_000)
    r = client.get("/requirements", params={"limit": 100})
    assert r.status_code == 200
    assert len(r.json()) == 100
    assert r.headers["X-Total-Count"] == "10000"
    assert r.json()[0]["id"] == "FR-00000"
    r2 = client.get("/requirements", params={"limit": 100, "offset": 9950})
    assert [x["id"] for x in r2.json()][0] == "FR-09950" and len(r2.json()) == 50


def test_default_returns_everything_for_existing_clients(client):
    for i in range(3):
        make_req(client, title=f"r{i}")
    r = client.get("/requirements")
    assert len(r.json()) == 3 and r.headers["X-Total-Count"] == "3"


def test_total_counts_filtered_matches_not_page(client):
    make_req(client, title="a", priority="high")
    make_req(client, title="b", priority="low")
    r = client.get("/requirements", params={"priority": "high", "limit": 1})
    assert len(r.json()) == 1 and r.headers["X-Total-Count"] == "1"


def test_bad_paging_values_are_rejected(client):
    assert client.get("/requirements", params={"limit": 0}).status_code == 422
    assert client.get("/requirements", params={"offset": -1}).status_code == 422
