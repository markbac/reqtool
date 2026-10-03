"""UI-14: iterations without a methodology are returned with the default."""
from tests.conftest import make_req  # noqa: F401  (keeps conftest fixtures importable)


def test_created_without_methodology_lists_with_default(client):
    assert client.post("/iterations", json={"id": "s1", "title": "S"}).status_code == 201
    rows = {i["id"]: i for i in client.get("/iterations").json()}
    assert rows["s1"]["methodology"] == "scrum"


def test_explicit_methodology_is_kept(client):
    client.post("/iterations", json={"id": "w1", "title": "W", "methodology": "waterfall"})
    rows = {i["id"]: i for i in client.get("/iterations").json()}
    assert rows["w1"]["methodology"] == "waterfall"
