"""#341: parent and child rules over the API: checks, roll-up, force with a reason, roles and the report."""
import pytest
from fastapi.testclient import TestClient

from reqtool import workflow_rules as wr
from reqtool.api import create_app
from reqtool.auth import UserStore
from tests.conftest import make_req

PW = "correct-horse-battery"


def set_rules(client, checks="error", changes="auto", **tweak):
    body = wr.default_rules(checks, changes)
    body.update(tweak)
    r = client.put("/rules", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def move(client, uid, to, **extra):
    return client.post(f"/requirements/{uid}/transition", json={"to_state": to, **extra})


def status(client, uid):
    return client.get(f"/requirements/{uid}").json()["status"]


@pytest.fixture
def chain(client):
    """epic > feature > two stories, all in the backlog."""
    epic = make_req(client, title="E", req_type="epic")
    feat = make_req(client, title="F", req_type="feature", parentId=epic["uid"])
    s1 = make_req(client, title="S1", req_type="story", parentId=feat["uid"])
    s2 = make_req(client, title="S2", req_type="story", parentId=feat["uid"])
    return epic, feat, s1, s2


class TestConfig:
    def test_get_returns_the_rules_and_no_problems(self, client):
        set_rules(client)
        body = client.get("/rules").json()
        assert body["problems"] == [] and {r["kind"] for r in body["rules"]} >= {"up", "down", "start", "complete"}

    def test_a_bad_rule_set_is_refused_and_nothing_changes(self, client):
        set_rules(client)
        bad = {"override": "editor", "rules": [{"id": "x", "kind": "up", "mode": "auto"}]}
        r = client.put("/rules", json=bad)
        assert r.status_code == 422 and "mode must be one of" in r.text
        assert len(client.get("/rules").json()["rules"]) == len(wr.default_rules()["rules"])

    def test_the_rules_survive_a_reload(self, client_with_store):
        client, store = client_with_store
        set_rules(client, "error", "auto")
        store.load()
        assert store.hierarchy.rules.rules[0].mode == "error"

    def test_a_repository_with_no_rules_behaves_as_before(self, client, chain):
        epic, feat, s1, _ = chain
        assert move(client, epic["uid"], "cancelled").status_code == 200
        r = move(client, s1["uid"], "in_progress")
        assert r.status_code == 200 and "rules" not in r.json()


class TestRollup:
    def test_story_start_moves_the_feature_and_epic(self, client, chain):
        epic, feat, s1, _ = chain
        set_rules(client, "off", "auto")
        r = move(client, s1["uid"], "in_progress")
        assert r.status_code == 200
        applied = r.json()["rules"]["applied"]
        assert [(a["id"], a["to"]) for a in applied][:2] == [(feat["id"], "in_progress"), (epic["id"], "in_progress")]
        assert status(client, feat["uid"]) == status(client, epic["uid"]) == "in_progress"

    def test_automatic_moves_are_in_the_history_with_the_rule_as_actor(self, client, chain):
        _, feat, s1, _ = chain
        set_rules(client, "off", "auto")
        move(client, s1["uid"], "in_progress")
        last = client.get(f"/requirements/{feat['uid']}").json()["history"][-1]
        assert last["modified_by"].startswith("rule: ") and "because" in last["summary"]

    def test_suggest_mode_proposes_and_changes_nothing(self, client, chain):
        _, feat, s1, _ = chain
        set_rules(client, "off", "suggest")
        r = move(client, s1["uid"], "in_progress").json()
        assert [s["id"] for s in r["rules"]["suggested"]] == [feat["id"]]
        assert status(client, feat["uid"]) == "backlog"

    def test_last_child_done_completes_the_parent(self, client, chain):
        _, feat, s1, s2 = chain
        set_rules(client, "off", "auto")
        for uid in (s1["uid"], s2["uid"]):
            move(client, uid, "in_progress")
        move(client, s1["uid"], "done")
        assert status(client, feat["uid"]) == "in_progress"
        move(client, s2["uid"], "done")
        assert status(client, feat["uid"]) == "done"

    def test_a_parent_that_cannot_move_is_a_warning_on_the_childs_save(self, client, chain):
        _, feat, s1, _ = chain
        set_rules(client, "off", "auto")
        assert client.post("/workflows", json={"id": "sprint_owner", "definition": _sprint_with_guard(client)}).status_code == 201
        assert client.put("/hierarchy/types/feature/workflow", json={"workflow": "sprint_owner"}).status_code == 200
        r = move(client, s1["uid"], "in_progress")
        assert r.status_code == 200
        blocked = r.json()["rules"]["blocked"]
        assert blocked and blocked[0]["id"] == feat["id"] and "owner" in blocked[0]["reason"]
        assert status(client, s1["uid"]) == "in_progress" and status(client, feat["uid"]) == "backlog"

    def test_it_works_through_a_plain_update_too(self, client, chain):
        _, feat, s1, _ = chain
        set_rules(client, "off", "auto")
        r = client.put(f"/requirements/{s1['uid']}", json={"status": "in_progress"})
        assert r.status_code == 200 and status(client, feat["uid"]) == "in_progress"

    def test_cascade_cancel(self, client, chain):
        _, feat, s1, s2 = chain
        body = wr.default_rules("off", "off")
        body["rules"][-1]["mode"] = "auto"
        assert client.put("/rules", json=body).status_code == 200
        move(client, s1["uid"], "in_progress")
        move(client, feat["uid"], "cancelled")
        assert status(client, s1["uid"]) == status(client, s2["uid"]) == "cancelled"


def _sprint_with_guard(client):
    wf = client.get("/workflows/sprint").json()["definition"]
    wf["guards"]["in_progress"] = {"requires_fields": ["owner"], "message": "Field 'owner' is required"}
    return wf


class TestChecks:
    def test_child_cannot_start_under_a_cancelled_ancestor(self, client, chain):
        epic, _, s1, _ = chain
        move(client, epic["uid"], "cancelled")
        set_rules(client, "error", "off")
        r = move(client, s1["uid"], "in_progress")
        assert r.status_code == 409
        body = r.json()["detail"]
        assert body["error"] == "workflow_guard" and body["rules"][0]["rule"] == "no-start-under-closed"
        assert "two levels up" in body["message"] and body["can_force"] is True
        assert status(client, s1["uid"]) == "backlog"

    def test_closing_a_parent_with_open_descendants_is_blocked_in_error_and_warned_in_warn(self, client, chain):
        _, feat, s1, s2 = chain
        move(client, feat["uid"], "in_progress")
        set_rules(client, "error", "off")
        r = move(client, feat["uid"], "done")
        assert r.status_code == 409 and s1["id"] in r.json()["detail"]["message"]
        set_rules(client, "warn", "off")
        r = move(client, feat["uid"], "done")
        assert r.status_code == 200 and r.json()["rules"]["warnings"][0]["rule"] == "finish-children-first"

    def test_the_transition_options_carry_checks_and_roll_ups(self, client, chain):
        epic, feat, s1, _ = chain
        move(client, epic["uid"], "cancelled")
        set_rules(client, "error", "suggest")
        options = {o["to"]: o for o in client.get(f"/requirements/{s1['uid']}/transitions").json()["transitions"]}
        assert options["in_progress"]["rules"]["checks"][0]["mode"] == "error"
        assert options["cancelled"]["rules"]["checks"] == []

    def test_preview_changes_nothing(self, client, chain):
        _, feat, s1, _ = chain
        set_rules(client, "off", "auto")
        p = client.post("/rules/preview", json={"uid": s1["uid"], "to_state": "in_progress"}).json()
        assert p["auto"][0]["id"] == feat["id"] and status(client, feat["uid"]) == "backlog"


class TestForce:
    def _blocked(self, client, chain):
        epic, _, s1, _ = chain
        move(client, epic["uid"], "cancelled")
        set_rules(client, "error", "off")
        return s1["uid"]

    def test_force_needs_a_reason(self, client, chain):
        uid = self._blocked(client, chain)
        r = move(client, uid, "in_progress", force=True)
        assert r.status_code == 422 and "reason is required" in r.text
        assert move(client, uid, "in_progress", force=True, reason="   ").status_code == 422

    def test_forcing_records_who_why_and_the_rule(self, client, chain):
        uid = self._blocked(client, chain)
        r = move(client, uid, "in_progress", force=True, reason="Customer asked for it")
        assert r.status_code == 200 and r.json()["rules"]["forced"] == ["no-start-under-closed"]
        item = client.get(f"/requirements/{uid}").json()
        assert item["attributes"]["forced"]["reason"] == "Customer asked for it"
        assert any("Forced past no-start-under-closed" in h["summary"] for h in item["history"])
        listed = client.get("/rules/overrides").json()["overrides"]
        assert [o["uid"] for o in listed] == [uid] and listed[0]["by"] == "user"

    def test_force_works_through_update_and_warn_rules_need_no_force(self, client, chain):
        uid = self._blocked(client, chain)
        r = client.put(f"/requirements/{uid}", json={"status": "in_progress", "force": True, "reason": "ok"})
        assert r.status_code == 200 and status(client, uid) == "in_progress"
        assert "force" not in client.get(f"/requirements/{uid}").json()

    def test_a_forced_item_leaves_the_report_when_it_moves_on(self, client, chain):
        uid = self._blocked(client, chain)
        move(client, uid, "in_progress", force=True, reason="ok")
        move(client, uid, "cancelled")
        assert client.get("/rules/overrides").json()["overrides"] == []

    def test_a_forced_parent_is_not_reverted_by_the_next_roll_up(self, client, chain):
        _, feat, s1, s2 = chain
        set_rules(client, "error", "auto")
        move(client, s1["uid"], "in_progress")        # rolls the feature up to in_progress
        move(client, s2["uid"], "in_progress")
        move(client, feat["uid"], "done", force=True, reason="Rest is out of scope")
        move(client, s1["uid"], "done")               # not all children done, nothing to undo either way
        assert status(client, feat["uid"]) == "done"


@pytest.fixture
def secured(repo_root):
    users = UserStore(repo_root)
    for name, role in (("root", "admin"), ("ed", "editor"), ("vw", "viewer")):
        users.create_user(name, PW, role=role)
    return TestClient(create_app(repo_root, auth_mode="required"))


def _h(c, name):
    t = c.post("/auth/login", json={"username": name, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


class TestRoles:
    def _setup(self, c, **tweak):
        admin = _h(c, "root")
        epic = c.post("/requirements", json={"title": "E", "req_type": "epic"}, headers=admin).json()
        story = c.post("/requirements", json={"title": "S", "req_type": "story", "parentId": epic["uid"]},
                       headers=admin).json()
        rules = wr.default_rules("error", "off")
        rules.update(tweak)
        c.post(f"/requirements/{epic['uid']}/transition", json={"to_state": "cancelled"}, headers=admin)
        assert c.put("/rules", json=rules, headers=admin).status_code == 200
        return story["uid"]

    def test_only_admins_edit_the_rules(self, secured):
        body = wr.default_rules()
        assert secured.put("/rules", json=body, headers=_h(secured, "ed")).status_code == 403
        assert secured.put("/rules", json=body, headers=_h(secured, "root")).status_code == 200
        assert secured.get("/rules", headers=_h(secured, "vw")).status_code == 200

    def test_editors_can_force_by_default(self, secured):
        uid = self._setup(secured)
        r = secured.post(f"/requirements/{uid}/transition", headers=_h(secured, "ed"),
                         json={"to_state": "in_progress", "force": True, "reason": "agreed in stand-up"})
        assert r.status_code == 200
        assert secured.get("/rules/overrides", headers=_h(secured, "ed")).json()["overrides"][0]["by"] == "ed"

    def test_when_only_admins_may_force_an_editor_is_refused(self, secured):
        uid = self._setup(secured, override="admin")
        blocked = secured.post(f"/requirements/{uid}/transition", headers=_h(secured, "ed"),
                               json={"to_state": "in_progress"})
        assert blocked.status_code == 409 and blocked.json()["detail"]["can_force"] is False
        forced = secured.post(f"/requirements/{uid}/transition", headers=_h(secured, "ed"),
                              json={"to_state": "in_progress", "force": True, "reason": "x"})
        assert forced.status_code == 403
        assert secured.post(f"/requirements/{uid}/transition", headers=_h(secured, "root"),
                            json={"to_state": "in_progress", "force": True, "reason": "x"}).status_code == 200

    def test_none_means_nobody_can_force(self, secured):
        uid = self._setup(secured, override="none")
        r = secured.post(f"/requirements/{uid}/transition", headers=_h(secured, "root"),
                         json={"to_state": "in_progress", "force": True, "reason": "x"})
        assert r.status_code == 403

    def test_a_viewer_cannot_move_anything(self, secured):
        uid = self._setup(secured)
        r = secured.post(f"/requirements/{uid}/transition", headers=_h(secured, "vw"),
                         json={"to_state": "in_progress", "force": True, "reason": "x"})
        assert r.status_code == 403


class TestBulkAndCli:
    def test_bulk_status_change_respects_error_rules_and_rolls_up(self, client, chain):
        epic, feat, s1, s2 = chain
        move(client, epic["uid"], "cancelled")
        set_rules(client, "error", "auto")
        r = client.post("/requirements/bulk", json={"uids": [s1["uid"]], "fields": {"status": "in_progress"}}).json()
        assert r["failed"] == [s1["uid"]] and "two levels up" in r["errors"][s1["uid"]]

    def test_bulk_roll_up(self, client, chain):
        _, feat, s1, s2 = chain
        set_rules(client, "off", "auto")
        r = client.post("/requirements/bulk", json={"uids": [s1["uid"], s2["uid"]], "fields": {"status": "in_progress"}})
        assert r.status_code == 200 and status(client, feat["uid"]) == "in_progress"

    def test_validate_rules_reports_the_rule_set_and_items_that_break_it(self, client_with_store, repo_root):
        from click.testing import CliRunner
        from reqtool.cli import cli
        client, _ = client_with_store
        epic = make_req(client, title="E", req_type="epic")
        story = make_req(client, title="S", req_type="story", parentId=epic["uid"])
        move(client, story["uid"], "in_progress")
        move(client, epic["uid"], "cancelled")
        set_rules(client, "error", "off")
        out = CliRunner().invoke(cli, ["validate", "--rules", "--repo", str(repo_root)])
        assert out.exit_code == 1 and "no-start-under-closed" in out.output
        move(client, story["uid"], "cancelled")
        fixed = CliRunner().invoke(cli, ["validate", "--rules", "--repo", str(repo_root)])
        assert "no-start-under-closed" not in fixed.output, fixed.output

    def test_validate_rules_shows_forced_items_as_forced_not_failing(self, client_with_store, repo_root):
        from click.testing import CliRunner
        from reqtool.cli import cli
        client, _ = client_with_store
        epic = make_req(client, title="E", req_type="epic")
        story = make_req(client, title="S", req_type="story", parentId=epic["uid"])
        move(client, epic["uid"], "cancelled")
        set_rules(client, "error", "off")
        move(client, story["uid"], "in_progress", force=True, reason="agreed")
        out = CliRunner().invoke(cli, ["validate", "--rules", "--repo", str(repo_root)])
        lines = [ln for ln in out.output.splitlines() if "no-start-under-closed" in ln]
        assert lines and all(ln.startswith("Forced") for ln in lines), out.output

    def test_migrate_adds_the_rules_switched_off(self, repo_root):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.commands.migrate import migrate_rules
        from reqtool.fileio import load_yaml, save_yaml
        from reqtool.stores.hierarchy_store import default_hierarchy_data
        save_yaml(repo_root / ".reqtool" / "hierarchy.yaml", default_hierarchy_data())
        assert migrate_rules(repo_root) is True and migrate_rules(repo_root) is False
        rules = load_yaml(repo_root / ".reqtool" / "hierarchy.yaml")["rules"]["rules"]
        assert rules and all(r["mode"] == "off" for r in rules)
