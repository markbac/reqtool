"""#378: the Work area's backlog: work items as a ranked tree with roll-ups, and reordering."""
from tests.conftest import make_req


def _tree(client):
    return client.get("/work/backlog").json()["items"]


def test_the_backlog_holds_work_items_only_as_a_tree(client):
    make_req(client, title="Need", req_type="stakeholder_need")
    epic = make_req(client, title="Epic", req_type="epic")
    s1 = make_req(client, title="One", req_type="story", parentId=epic["uid"])
    client.put(f"/requirements/{s1['uid']}", json={"estimate": 3})
    make_req(client, title="Two", req_type="story", parentId=epic["uid"])
    make_req(client, title="An issue", req_type="issue")
    tree = _tree(client)
    assert [n["id"] for n in tree] == [epic["id"]]
    kids = tree[0]["children"]
    assert [k["title"] for k in kids] == ["One", "Two"]
    assert tree[0]["total_points"] == 3 and tree[0]["done_points"] == 0 and tree[0]["progress_pct"] == 0
    assert kids[0]["linked_requirements"] == 0


def test_items_are_reordered_within_their_parent(client):
    epic = make_req(client, title="Epic", req_type="epic")
    a = make_req(client, title="A", req_type="story", parentId=epic["uid"])
    b = make_req(client, title="B", req_type="story", parentId=epic["uid"])
    c = make_req(client, title="C", req_type="story", parentId=epic["uid"])
    r = client.post(f"/work/backlog/{c['uid']}/rank", json={"before": a["uid"]})
    assert r.status_code == 200, r.text
    assert [k["title"] for k in _tree(client)[0]["children"]] == ["C", "A", "B"]
    client.post(f"/work/backlog/{c['uid']}/rank", json={"after": b["id"]})       # ids work as well as uids
    assert [k["title"] for k in _tree(client)[0]["children"]] == ["A", "B", "C"]


def test_reordering_next_to_an_item_with_another_parent_is_refused(client):
    e1 = make_req(client, title="E1", req_type="epic")
    e2 = make_req(client, title="E2", req_type="epic")
    a = make_req(client, title="A", req_type="story", parentId=e1["uid"])
    b = make_req(client, title="B", req_type="story", parentId=e2["uid"])
    r = client.post(f"/work/backlog/{a['uid']}/rank", json={"before": b["uid"]})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "different_parent"


def test_the_board_shows_work_items_only_in_workflow_order(client):
    make_req(client, title="Need", req_type="stakeholder_need")
    make_req(client, title="Req", req_type="functional")
    make_req(client, title="Story", req_type="story")
    make_req(client, title="Issue", req_type="issue")
    board = client.get("/kanban").json()
    titles = [c["title"] for cards in board["columns"].values() for c in cards]
    assert titles == ["Story"]
    states = [s for s in board["columns"] if s != "_uncolumned"]
    assert states[0] == "backlog" and states[-1] == "cancelled"
