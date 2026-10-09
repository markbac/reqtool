"""The transition options the item viewer offers, and moving an item with its missing data in one call."""
import pytest

SAFETY = {"title": "Brake", "req_type": "safety"}


def _options(client, uid):
    return {t["to"]: t for t in client.get(f"/requirements/{uid}/transitions").json()["transitions"]}


def _to_reviewed(client, uid):
    for status in ("in_review", "reviewed"):
        r = client.put(f"/requirements/{uid}", json={"status": status})
        assert r.status_code == 200, r.text


def test_unguarded_move_lists_no_requirements(client):
    uid = client.post("/requirements", json={"title": "Pump"}).json()["uid"]
    opts = _options(client, uid)
    assert list(opts) == ["in_review"]
    assert opts["in_review"]["requires"]["fields"] == []
    assert opts["in_review"]["problem"] is None


def test_guarded_move_reports_what_is_missing(client):
    uid = client.post("/requirements", json=SAFETY).json()["uid"]
    _to_reviewed(client, uid)
    approve = _options(client, uid)["approved"]
    fields = {f["path"]: f for f in approve["requires"]["fields"]}
    assert fields["content.description"]["filled"] is False
    assert approve["requires"]["acceptance_criteria"] is True
    assert approve["requires"]["has_acceptance_criteria"] is False
    assert approve["problem"]
    assert approve["requires"]["message"]


def test_one_put_with_fields_and_status_passes(client):
    uid = client.post("/requirements", json=SAFETY).json()["uid"]
    _to_reviewed(client, uid)
    r = client.put(f"/requirements/{uid}", json={"status": "approved"})
    assert r.status_code == 409
    full = {
        "status": "approved", "safety_classification": "ASIL-B",
        "content": {"description": "Brakes shall stop the car.", "rationale": "Safety"},
        "acceptance_criteria": [{"id": "AC-1", "text": "Stops in 40 m"}],
    }
    r = client.put(f"/requirements/{uid}", json=full)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert "deprecated" in _options(client, uid)


def test_unknown_item_is_404(client):
    assert client.get("/requirements/does-not-exist/transitions").status_code == 404


def test_filling_the_fields_does_not_allow_skipping_a_state(client):
    uid = client.post("/requirements", json=SAFETY).json()["uid"]
    full = {
        "status": "approved", "safety_classification": "ASIL-B",
        "content": {"description": "Brakes shall stop the car.", "rationale": "Safety"},
        "acceptance_criteria": [{"id": "AC-1", "text": "Stops in 40 m"}],
    }
    r = client.put(f"/requirements/{uid}", json=full)
    assert r.status_code == 409, r.text
    assert client.get(f"/requirements/{uid}").json()["status"] == "draft"
