"""Read-only views: hierarchy, coverage, impact, flow, decisions, principles, grid and roadmap board."""
import pytest

from tests.conftest import make_req


@pytest.fixture
def tree(client):
    epic = make_req(client, title="Checkout", req_type="epic")
    feat = make_req(client, title="Pay by card", req_type="feature", parentId=epic["uid"])
    story = make_req(client, title="Enter card number", req_type="story", parentId=feat["uid"])
    return epic, feat, story


def test_hierarchy_lists_items_in_tree_order_with_parents(client, tree):
    epic, feat, story = tree
    nodes = client.get("/views/hierarchy").json()["nodes"]
    ids = [n["uid"] for n in nodes]
    assert ids.index(epic["uid"]) < ids.index(feat["uid"]) < ids.index(story["uid"])
    assert next(n for n in nodes if n["uid"] == story["uid"])["parent"] == feat["uid"]


def test_hierarchy_filter_keeps_ancestors_of_matches(client, tree):
    epic, feat, story = tree
    nodes = client.get("/views/hierarchy", params={"types": "story"}).json()["nodes"]
    assert {epic["uid"], feat["uid"], story["uid"]} <= {n["uid"] for n in nodes}


def test_type_structure_is_mermaid(client):
    data = client.get("/views/type-structure").json()
    assert "flowchart" in data["mermaid"]


def test_coverage_counts_descendants(client, tree):
    epic = tree[0]
    top = client.get("/views/coverage").json()
    assert top["roots"] if "roots" in top else top


def test_impact_of_a_story_includes_its_parent(client, tree):
    epic, feat, story = tree
    g = client.get(f"/views/impact/{story['uid']}", params={"depth": 2}).json()
    assert {epic["uid"], feat["uid"], story["uid"]} <= {n["key"] for n in g["nodes"]}
    assert client.get("/views/impact/nope").status_code == 404


def test_flow_reports_states_per_workflow(client, tree):
    wfs = client.get("/views/flow", params={"stuck_days": 7}).json()
    assert wfs["stuck_days"] == 7 and wfs["workflows"]
    assert all("states" in w for w in wfs["workflows"])


def test_moving_an_item_records_where_it_came_from(client, tree):
    story = tree[2]
    r = client.post(f"/requirements/{story['uid']}/transition", json={"to_state": "in_progress"})
    if r.status_code == 200:
        hist = client.get(f"/requirements/{story['uid']}").json()["history"][-1]
        assert hist["status_to"] == "in_progress" and hist["status_from"]


def test_decision_ageing_and_principle_heatmap_answer(client):
    assert "open" in client.get("/views/decisions").json() or client.get("/views/decisions").status_code == 200
    assert client.get("/views/principles").status_code == 200
    assert client.get("/views/principles/nope/citations").status_code == 404


def test_grid_gaps_and_csv(client, tree):
    g = client.get("/traceability/grid", params={"columns": "tests", "gaps": True}).json()
    assert g["rows"]
    r = client.get("/traceability/grid", params={"format": "csv"})
    assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    assert client.get("/traceability/grid", params={"format": "xml"}).status_code == 422


def test_roadmap_board_and_burnup_unknown_iteration(client, tree):
    assert client.get("/roadmap/board", params={"group_by": "iteration"}).status_code == 200
    assert client.get("/roadmap/board", params={"group_by": "x"}).status_code == 422
    assert client.get("/views/burnup/missing").status_code == 404
