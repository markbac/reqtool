"""The data behind the views: time in state, stuck items, caps and the grid."""
from datetime import datetime, timedelta, timezone

from reqtool.features import visuals
from tests.conftest import make_req


def test_a_move_records_where_it_came_from_and_when_the_item_entered_its_state(client_with_store):
    client, store = client_with_store
    story = make_req(client, title="A story", req_type="story")
    r = client.post(f"/requirements/{story['uid']}/transition", json={"to_state": "ready"})
    assert r.status_code == 200, r.text
    entry = client.get(f"/requirements/{story['uid']}").json()["history"][-1]
    assert entry["status_from"] == "backlog" and entry["status_to"] == "ready"
    assert visuals.entered_status_at({**entry, "status": "ready", "history": [entry], "created": "2020-01-01T00:00:00Z"}) is not None


def test_items_that_sat_too_long_are_stuck_and_the_limit_can_be_set_per_state(client_with_store):
    client, _ = client_with_store
    story = make_req(client, title="Waiting", req_type="story")
    from reqtool.store import Store
    fresh = Store(client_with_store[1].root)
    fresh.load()
    later = datetime.now(timezone.utc) + timedelta(days=20)
    flow = visuals.flow(fresh, now=later)
    row = next(s for w in flow["workflows"] if "story" in w["types"] for s in w["states"] if s["state"] == "backlog")
    assert row["stuck_count"] >= 1 and any(i["uid"] == story["uid"] for i in row["stuck"])
    assert visuals.flow(fresh, stuck_days=60, now=later)["stuck_days"] == 60
    calm = visuals.flow(fresh, stuck_days=60, now=later)
    assert all(s["stuck_count"] == 0 for w in calm["workflows"] for s in w["states"])


def test_the_hierarchy_is_capped_and_says_so(client_with_store):
    client, store = client_with_store
    for i in range(5):
        make_req(client, title=f"Item {i}", req_type="story")
    from reqtool.store import Store
    fresh = Store(store.root)
    fresh.load()
    out = visuals.hierarchy_tree(fresh, limit=3)
    assert out["shown"] == 3 and out["capped"] and out["total"] >= 5


def test_the_grid_csv_has_a_header_and_one_row_per_requirement(client_with_store):
    client, store = client_with_store
    make_req(client, title="Lonely", req_type="story")
    from reqtool.store import Store
    fresh = Store(store.root)
    fresh.load()
    text = visuals.trace_grid_csv(visuals.trace_grid(fresh, "tests"))
    lines = text.strip().splitlines()
    assert lines[0].startswith("id,title,type,status") and len(lines) == 2


def test_flow_limits_come_from_hierarchy_yaml(repo_root):
    import yaml
    from reqtool.store import Store
    path = repo_root / ".reqtool" / "hierarchy.yaml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    data["flow"] = {"stuck_days": 3, "states": {"backlog": 1}}
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump(data))
    store = Store(repo_root)
    store.load()
    assert store.hierarchy.flow.stuck_days == 3 and store.hierarchy.flow.states == {"backlog": 1}
    assert visuals.flow(store)["stuck_days"] == 3
