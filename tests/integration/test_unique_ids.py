"""DAT-12: user-supplied IDs are validated, unique, and usable for lookup."""
import pytest
from tests.conftest import make_req
from reqtool.validation import validate_all


def test_duplicate_id_on_create_is_409(client):
    make_req(client, id="FR-900")
    r = client.post("/requirements", json={"title": "again", "id": "FR-900"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "duplicate_id"


@pytest.mark.parametrize("bad", ["a/b", "../../esc", "has space", "..", "x\\y", ""])
def test_bad_format_rejected(client, bad):
    r = client.post("/requirements", json={"title": "t", "id": bad})
    # empty id means "auto-allocate"; everything else is a 422
    assert r.status_code == (201 if bad == "" else 422)


def test_rename_to_existing_id_is_409_but_own_id_ok(client):
    a = make_req(client, id="FR-1")
    b = make_req(client, id="FR-2")
    assert client.put(f"/requirements/{b['uid']}", json={"id": "FR-1"}).status_code == 409
    assert client.put(f"/requirements/{a['uid']}", json={"id": "FR-1", "title": "same id"}).status_code == 200
    assert client.put(f"/requirements/{b['uid']}", json={"id": "FR-3"}).status_code == 200


def test_deleted_ids_can_be_reused(client):
    a = make_req(client, id="FR-7")
    client.delete(f"/requirements/{a['uid']}")
    assert client.post("/requirements", json={"title": "t", "id": "FR-7"}).status_code == 201


def test_lookup_by_human_id(client):
    a = make_req(client, id="FR-42")
    r = client.get("/requirements/FR-42")
    assert r.status_code == 200 and r.json()["uid"] == a["uid"]
    assert client.get("/requirements/NOPE-1").status_code == 404


def test_bulk_reports_duplicate_per_item(client):
    make_req(client, id="FR-1")
    b = make_req(client, id="FR-2")
    r = client.post("/requirements/bulk", json={"uids": [b["uid"]], "fields": {"id": "FR-1"}}).json()
    assert r["failed"] == [b["uid"]] and "already used" in r["errors"][b["uid"]]


def test_clone_ids_stay_unique(client):
    a = make_req(client, id="FR-5")
    ids = {client.post(f"/requirements/{a['uid']}/clone").json()["id"] for _ in range(3)}
    assert ids == {"FR-5-COPY", "FR-5-COPY2", "FR-5-COPY3"}


def test_validation_flags_existing_duplicates(client):
    a = make_req(client, id="FR-1")
    b = make_req(client, id="FR-2")
    client.app.state.store.requirements[b["uid"]]["id"] = "FR-1"  # as if edited by hand / merged from a branch
    errs = [e for e in validate_all(client.app.state.store)["errors"] if e["code"] == "duplicate_id"]
    assert {e["uid"] for e in errs} == {a["uid"], b["uid"]}
