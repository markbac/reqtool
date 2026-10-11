"""Issue intake: raise an issue, triage it, and only a confirmed defect becomes defect work."""
import pytest

from tests.conftest import make_req

DESC = {"description": "Pressing Save does nothing."}


def move(client, uid, to, **extra):
    return client.post(f"/requirements/{uid}/transition", json={"to_state": to, **extra})


def put(client, uid, **fields):
    r = client.put(f"/requirements/{uid}", json=fields)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def issue(client):
    return make_req(client, title="Save button does nothing", req_type="issue", content=DESC)


def triage(client, issue):
    put(client, issue["uid"], assignee="tess")
    assert move(client, issue["uid"], "in_triage").status_code == 200


def test_the_default_repository_has_an_issue_type_and_calls_bugs_defects(client):
    types = client.get("/hierarchy/types").json()
    assert types["issue"]["workflow"] == "triage" and types["issue"]["id_prefix"] == "ISS"
    assert types["bug"]["label"] == "Defect"


def test_an_issue_starts_reported_and_triage_needs_an_owner(client, issue):
    assert issue["status"] == "reported" and issue["id"].startswith("ISS-")
    r = move(client, issue["uid"], "in_triage")
    assert r.status_code == 409 and "own the triage" in r.json()["detail"]["message"]
    triage(client, issue)


def test_it_cannot_jump_from_reported_to_a_decision(client, issue):
    assert move(client, issue["uid"], "defect").status_code == 409


@pytest.mark.parametrize("outcome,needs", [
    ("defect", {"priority": "high", "custom_fields": {"triage_note": "Reproduced on 1.2"}}),
    ("user_error", {"custom_fields": {"triage_note": "Use Ctrl+S"}}),
    ("enhancement", {"custom_fields": {"triage_note": "Wants autosave"}}),
    ("not_reproducible", {"custom_fields": {"triage_note": "Tried 1.1 and 1.2"}}),
    ("needs_info", {"custom_fields": {"triage_note": "Which browser?"}}),
    ("duplicate", {"custom_fields": {"duplicate_of": "ISS-001"}}),
])
def test_each_decision_needs_its_reason_and_then_succeeds(client, issue, outcome, needs):
    triage(client, issue)
    refused = move(client, issue["uid"], outcome)
    assert refused.status_code == 409, outcome
    put(client, issue["uid"], **needs)
    assert move(client, issue["uid"], outcome).status_code == 200
    assert client.get(f"/requirements/{issue['uid']}").json()["status"] == outcome


def test_a_defect_goes_on_to_be_fixed_and_closed(client, issue):
    triage(client, issue)
    put(client, issue["uid"], priority="high", custom_fields={"triage_note": "Reproduced"})
    for step in ("defect", "fixing", "fixed", "closed"):
        assert move(client, issue["uid"], step).status_code == 200, step


def test_closed_outcomes_can_be_reopened_for_triage(client, issue):
    triage(client, issue)
    put(client, issue["uid"], custom_fields={"triage_note": "Use Ctrl+S"})
    move(client, issue["uid"], "user_error")
    assert move(client, issue["uid"], "in_triage").status_code == 200


def test_transitions_name_what_each_decision_needs(client, issue):
    triage(client, issue)
    options = {o["to"]: o for o in client.get(f"/requirements/{issue['uid']}/transitions").json()["transitions"]}
    assert set(options) == {"defect", "user_error", "enhancement", "duplicate", "not_reproducible", "needs_info"}
    assert [f["path"] for f in options["defect"]["requires"]["fields"]] == ["priority", "custom_fields.triage_note"]
    assert options["duplicate"]["requires"]["fields"][0]["label"] == "Duplicate of"


class TestRaise:
    def test_a_confirmed_defect_is_raised_as_a_linked_defect_item(self, client, issue):
        triage(client, issue)
        put(client, issue["uid"], priority="high", custom_fields={"triage_note": "Reproduced"})
        move(client, issue["uid"], "defect")
        r = client.post(f"/requirements/{issue['uid']}/raise", json={})
        assert r.status_code == 201, r.text
        made = r.json()
        assert made["req_type"] == "bug" and made["title"] == issue["title"] and made["priority"] == "high"
        assert made["content"]["description"] == DESC["description"]
        assert made["relationships"][0]["type"] == "derived_from" and made["relationships"][0]["target"]["uid"] == issue["uid"]
        incoming = client.get(f"/requirements/{issue['uid']}/relationships").json()["incoming"]
        assert incoming == [{"source_uid": made["uid"], "source_id": made["id"], "type": "derived_from"}]

    def test_an_enhancement_request_is_raised_as_a_story(self, client, issue):
        triage(client, issue)
        put(client, issue["uid"], custom_fields={"triage_note": "Wants autosave"})
        move(client, issue["uid"], "enhancement")
        assert client.post(f"/requirements/{issue['uid']}/raise", json={}).json()["req_type"] == "story"

    def test_it_needs_a_type_when_the_status_has_no_default(self, client, issue):
        r = client.post(f"/requirements/{issue['uid']}/raise", json={})
        assert r.status_code == 422 and "which type" in r.json()["detail"]["message"]
        assert client.post(f"/requirements/{issue['uid']}/raise", json={"req_type": "task"}).status_code == 201
        assert client.post(f"/requirements/{issue['uid']}/raise", json={"req_type": "nope"}).status_code == 422
