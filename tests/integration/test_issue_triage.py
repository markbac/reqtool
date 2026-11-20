"""Issue intake (#379): raise an issue, triage it, and triage turns it into work (the same record) or rejects it."""
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


def test_it_cannot_jump_from_reported_to_a_rejection_needing_triage(client, issue):
    assert move(client, issue["uid"], "user_error").status_code == 409


@pytest.mark.parametrize("outcome,needs", [
    ("user_error", {"custom_fields": {"triage_note": "Use Ctrl+S"}}),
    ("not_reproducible", {"custom_fields": {"triage_note": "Tried 1.1 and 1.2"}}),
    ("needs_info", {"custom_fields": {"triage_note": "Which browser?"}}),
    ("duplicate", {"custom_fields": {"duplicate_of": "ISS-001"}}),
    ("wont_do", {"custom_fields": {"triage_note": "Out of scope for this product"}}),
])
def test_each_rejection_needs_its_reason_and_then_succeeds(client, issue, outcome, needs):
    triage(client, issue)
    refused = move(client, issue["uid"], outcome)
    assert refused.status_code == 409, outcome
    put(client, issue["uid"], **needs)
    assert move(client, issue["uid"], outcome).status_code == 200
    assert client.get(f"/requirements/{issue['uid']}").json()["status"] == outcome


def test_closed_outcomes_can_be_reopened_for_triage(client, issue):
    triage(client, issue)
    put(client, issue["uid"], custom_fields={"triage_note": "Use Ctrl+S"})
    move(client, issue["uid"], "user_error")
    assert move(client, issue["uid"], "in_triage").status_code == 200


def test_transitions_name_what_each_decision_needs(client, issue):
    triage(client, issue)
    options = {o["to"]: o for o in client.get(f"/requirements/{issue['uid']}/transitions").json()["transitions"]}
    assert set(options) == {"user_error", "duplicate", "not_reproducible", "wont_do", "needs_info", "closed"}
    assert options["duplicate"]["requires"]["fields"][0]["label"] == "Duplicate of"


def t(client, uid, **body):
    return client.post(f"/requirements/{uid}/triage", json=body)


class TestTriage:
    def test_start_makes_the_person_triaging_the_owner(self, client, issue):
        r = t(client, issue["uid"], outcome="start", by="tess")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_triage" and r.json()["assignee"] == "tess"

    def test_making_it_a_defect_converts_the_same_record(self, client, issue):
        story = make_req(client, title="Save works", req_type="story")
        req = make_req(client, title="Save shall store the file", req_type="functional")
        client.post(f"/artefacts/{issue['uid']}/comments", json={"text": "Seen on 1.2", "author": "tess"})
        t(client, issue["uid"], outcome="start", by="tess")
        r = t(client, issue["uid"], outcome="defect", parent=story["uid"], link=req["id"], priority="high",
              note="Reproduced on 1.2", by="tess")
        assert r.status_code == 200, r.text
        bug = r.json()
        assert bug["uid"] == issue["uid"] and bug["req_type"] == "bug" and bug["id"].startswith("BG-")
        assert bug["status"] == "backlog" and bug["parentId"] == story["uid"] and bug["priority"] == "high"
        assert bug["aliases"] == [issue["id"]] and bug["converted_from"]["id"] == issue["id"]
        assert bug["relationships"][-1] == {"type": "traces_to", "target": {"uid": req["uid"], "id": req["id"]}}
        assert bug["custom_fields"]["triage_note"] == "Reproduced on 1.2"
        assert "Converted from issue" in bug["history"][-1]["summary"]
        # The old id still opens it, and its comments came with it.
        assert client.get(f"/requirements/{issue['id']}").json()["uid"] == issue["uid"]
        assert client.get(f"/artefacts/{issue['uid']}/comments").json()[0]["text"] == "Seen on 1.2"

    @pytest.mark.parametrize("outcome,typ", [("story", "story"), ("feature", "feature")])
    def test_an_enhancement_becomes_a_story_or_feature(self, client, issue, outcome, typ):
        made = t(client, issue["uid"], outcome=outcome).json()
        assert made["req_type"] == typ and made["converted_from"]["id"] == issue["id"]

    def test_rejecting_needs_a_reason_and_closes_the_issue(self, client, issue):
        t(client, issue["uid"], outcome="start", by="tess")
        r = t(client, issue["uid"], outcome="rejected", reason="duplicate", duplicate_of="ISS-001")
        assert r.status_code == 200 and r.json()["status"] == "duplicate" and r.json()["req_type"] == "issue"
        assert t(client, issue["uid"], outcome="rejected", reason="nope").status_code == 422

    def test_only_issues_are_triaged(self, client):
        story = make_req(client, title="S", req_type="story")
        assert t(client, story["uid"], outcome="defect").status_code == 422

    def test_the_work_area_lists_issues_and_what_they_became(self, client, issue):
        other = make_req(client, title="Graph blank", req_type="issue", content=DESC)
        t(client, other["uid"], outcome="story")
        q = client.get("/work/issues").json()
        assert [i["uid"] for i in q["issues"]] == [issue["uid"]]
        assert q["converted"] == [{"uid": other["uid"], "id": q["converted"][0]["id"], "title": "Graph blank",
                                   "status": "backlog", "req_type": "story", "converted_from": other["id"]}]


class TestRaiseStillWorks:
    def test_the_deprecated_raise_creates_a_linked_item(self, client, issue):
        r = client.post(f"/requirements/{issue['uid']}/raise", json={"req_type": "task"})
        assert r.status_code == 201
        assert r.json()["relationships"][0]["target"]["uid"] == issue["uid"]


def test_migration_handles_issues_left_in_the_old_triage_states(repo_root):
    from reqtool.commands.migrate import migrate_issues
    from reqtool.store import Store
    store = Store(repo_root); store.load()
    raised_from = store.create_requirement({"title": "Old defect", "req_type": "issue"})
    store.update_requirement(raised_from["uid"], {"status": "fixing"})
    bug = store.create_requirement({"title": "The fix", "req_type": "bug", "relationships": [
        {"type": "derived_from", "target": {"uid": raised_from["uid"], "id": raised_from["id"]}}]})
    lone = store.create_requirement({"title": "Old enhancement", "req_type": "issue"})
    store.update_requirement(lone["uid"], {"status": "planned"})

    assert migrate_issues(repo_root) == {"linked": 1, "converted": 1}
    assert migrate_issues(repo_root) == {"linked": 0, "converted": 0}
    store.load()
    assert store.requirements[raised_from["uid"]]["status"] == "closed"
    assert store.requirements[raised_from["uid"]]["converted_to"] == bug["uid"]
    became = store.requirements[lone["uid"]]
    assert became["req_type"] == "story" and became["status"] == "ready" and lone["id"] in became["aliases"]
