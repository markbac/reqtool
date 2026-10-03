"""MOD-10, MOD-13, UI-06 server side: roll-up summary, delivery board, ADR export."""
import pytest

from tests.conftest import make_req, make_tbd


def _mk(client, title, req_type, parent=None, **kw):
    body = {"title": title, "req_type": req_type, **kw}
    if parent:
        body["parentId"] = parent
    r = client.post("/requirements", json=body)
    assert r.status_code == 201, r.text
    return r.json()["uid"]


@pytest.fixture
def initiative(client):
    ini = _mk(client, "Init", "initiative")
    epic = _mk(client, "Epic", "epic", ini)
    s1 = _mk(client, "S1", "story", epic, estimate=3)
    s2 = _mk(client, "S2", "story", epic, estimate=1)
    client.post(f"/requirements/{s1}/transition", json={"to_state": "ready"})
    for st in ("in_progress", "in_review", "done"):
        client.post(f"/requirements/{s1}/transition", json={"to_state": st})
    return {"ini": ini, "epic": epic, "s1": s1, "s2": s2}


def test_summary_matches_progress_and_counts(client, initiative):
    u = initiative
    sm = client.get(f"/requirements/{u['ini']}/summary").json()
    assert sm["progress"] == client.get(f"/requirements/{u['ini']}/progress").json()
    assert sm["direct_children"] == 1 and sm["descendants"] == 3
    assert sm["by_type"] == {"epic": 1, "story": 2}
    assert sm["estimate_rollup"] == 4 and sm["progress"]["progress_pct"] == 75.0
    assert set(sm["validation"]) == {"errors", "warnings"}


def test_summary_lists_open_tbds_and_fields(client, initiative):
    t = make_tbd(client)
    client.put(f"/requirements/{initiative['s2']}", json={"links": [{"type": "tbd", "ref": t["uid"], "system": "reqtool"}]})
    client.put(f"/requirements/{initiative['ini']}", json={"custom_fields": {"outcome": "Ship"}})
    sm = client.get(f"/requirements/{initiative['ini']}/summary").json()
    assert sm["open_tbds"] == [t["id"]] and sm["fields"] == {"outcome": "Ship"}
    assert client.get("/requirements/nope/summary").status_code == 404


def test_tree_nodes_carry_progress_matching_the_api(client, initiative):
    tree = client.get("/requirements/tree?product=p").json()

    def find(nodes, uid):
        for n in nodes:
            if n["uid"] == uid:
                return n
            hit = find(n["children"], uid)
            if hit:
                return hit
    for key in ("ini", "epic"):
        node = find(tree, initiative[key])
        assert node["progress_pct"] == client.get(f"/requirements/{initiative[key]}/progress").json()["progress_pct"]
    assert "progress_pct" not in find(tree, initiative["s1"])


def test_board_excludes_strategic_and_systems_types(client, initiative):
    _mk(client, "Req", "functional")
    board = client.get("/kanban").json()
    types = {c["req_type"] for cards in board["columns"].values() for c in cards}
    assert types == {"epic", "story"}
    assert set(board["delivery_types"]) == {"epic", "feature", "story", "task", "bug", "spike"}
    assert client.get("/kanban?req_type=theme").status_code == 422


def test_board_keeps_cards_whose_status_has_no_column(repo_root):
    from reqtool.store import Store
    store = Store(repo_root); store.load()
    a = store.create_requirement({"title": "A", "req_type": "story"})
    b = store.create_requirement({"title": "B", "req_type": "story"})
    store.requirements[b["uid"]]["status"] = "no_such_state"
    board = store.build_kanban()
    assert [c["uid"] for c in board["columns"]["_uncolumned"]] == [b["uid"]]
    assert sum(len(v) for v in board["columns"].values()) == 2


def test_board_columns_are_the_union_of_workflows(repo_root):
    from reqtool.store import Store
    store = Store(repo_root); store.load()
    states = store.build_kanban()["states"]
    assert len(states) == len(set(states)) and "done" in states
    for t in store.delivery_types():
        wf = store.get_workflow_for_type(t)
        assert {s.id for s in wf.states} <= set(states)


def test_adr_export_contains_decisions_not_tbds(client):
    d = client.post("/decisions", json={"title": "Use REST"}).json()
    t = make_tbd(client, title="Pick a broker")
    md = client.get("/export/adr").text
    assert d["id"] in md and t["id"] not in md
    assert [x["uid"] for x in client.get("/decisions?type=decision").json()] == [d["uid"]]
    assert [x["uid"] for x in client.get("/decisions?type=tbd").json()] == [t["uid"]]
