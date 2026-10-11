"""An open question and the decision it became are linked, and each shows the other."""


def test_the_link_shows_from_both_ends(client):
    q = client.post("/tbds", json={"title": "Which queue?", "content": {"description": "Pick."}}).json()
    d = client.post("/decisions", json={"title": "Use Rabbit", "content": {"description": "Rabbit."}}).json()
    r = client.post(f"/tbds/{q['uid']}/resolve", json={"decision": "Rabbit", "linked_decision": d["uid"]})
    assert r.status_code == 200
    assert client.get(f"/tbds/{q['uid']}").json()["resolved_into"]["id"] == d["id"]
    assert [x["id"] for x in client.get(f"/decisions/{d['uid']}").json()["resolves"]] == [q["id"]]


def test_an_unresolved_question_links_to_nothing(client):
    q = client.post("/tbds", json={"title": "Open one", "content": {"description": "?"}}).json()
    got = client.get(f"/decisions/{q['uid']}").json()
    assert got["resolved_into"] is None and got["resolves"] == []


def test_both_routes_serve_the_same_item(client):
    q = client.post("/tbds", json={"title": "Alias", "content": {"description": "?"}}).json()
    assert client.get(f"/decisions/{q['uid']}").json()["uid"] == q["uid"]
    assert client.get("/tbds").status_code == 200
