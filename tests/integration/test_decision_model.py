"""MOD-12, 14, 15, 16, 17 and #371: one decision kind (open questions are pending decisions), accepting,
the migration of old TBDs, workflow and strategic fields."""
import shutil

import pytest
from click.testing import CliRunner

from reqtool.cli import cli
from reqtool.commands.migrate import migrate_decisions, migrate_tbds
from reqtool.store import Store
from reqtool.validation import validate_all
from tests.conftest import make_req, make_tbd, review_first


def test_a_question_is_a_pending_decision_and_tbds_is_an_alias(client):
    t = make_tbd(client)
    assert t["type"] == "decision" and t["status"] == "proposed"
    d = client.post("/decisions", json={"title": "Use REST"}).json()
    assert {x["uid"] for x in client.get("/decisions").json()} >= {t["uid"], d["uid"]}
    # /tbds lists pending decisions (both are pending), and is marked deprecated in the API description.
    assert {x["uid"] for x in client.get("/tbds").json()} == {t["uid"], d["uid"]}
    client.post(f"/decisions/{d['uid']}/accept", json={"decision": "REST", "resolved_by": "a"})
    assert [x["uid"] for x in client.get("/tbds").json()] == [t["uid"]]
    assert [x["uid"] for x in client.get("/decisions?status=proposed").json()] == [t["uid"]]
    assert client.app.openapi()["paths"]["/tbds"]["get"].get("deprecated") is True


def test_new_tbds_are_written_to_decisions_folder(client, repo_root):
    t = make_tbd(client)
    assert (repo_root / "decisions" / f"{t['uid']}.yaml").exists()
    assert not (repo_root / "tbds" / f"{t['uid']}.yaml").exists()


def test_migration_moves_legacy_files_and_is_idempotent(repo_root):
    store = Store(repo_root); store.load()
    t = store.create_tbd({"title": "Legacy"})
    (repo_root / "tbds").mkdir(exist_ok=True)
    shutil.move(repo_root / "decisions" / f"{t['uid']}.yaml", repo_root / "tbds" / f"{t['uid']}.yaml")
    store.load()
    assert t["uid"] in store.decisions  # still readable from tbds/ before migration

    assert migrate_tbds(repo_root) == {"moved": 1, "skipped": 0}
    assert migrate_tbds(repo_root) == {"moved": 0, "skipped": 0}
    assert not (repo_root / "tbds").exists()
    store.load()
    assert store.decisions[t["uid"]]["title"] == "Legacy"


def test_migration_leaves_conflicting_copies(repo_root):
    (repo_root / "tbds").mkdir(); (repo_root / "decisions").mkdir(exist_ok=True)
    (repo_root / "tbds" / "x.yaml").write_text("a: 1\n")
    (repo_root / "decisions" / "x.yaml").write_text("a: 2\n")
    assert migrate_tbds(repo_root) == {"moved": 0, "skipped": 1}
    assert (repo_root / "tbds" / "x.yaml").exists()


def test_migrate_command_round_trips_demo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(cli, ["init", "demo"])
    before = Store(tmp_path); before.load()
    r = CliRunner().invoke(cli, ["migrate", "--repo", str(tmp_path)])
    assert r.exit_code == 0, r.output
    after = Store(tmp_path); after.load()
    assert after.decisions == before.decisions
    assert not validate_all(after)["errors"]


def test_accept_requires_decision_text(client):
    t = make_tbd(client)
    assert client.post(f"/decisions/{t['uid']}/accept", json={"resolved_by": "me"}).status_code == 422
    assert client.post(f"/tbds/{t['uid']}/resolve", json={"decision": "  "}).status_code == 422
    assert client.get(f"/decisions/{t['uid']}").json()["status"] == "proposed"


def test_reject_closes_the_decision_with_a_reason(client):
    t = make_tbd(client)
    r = client.post(f"/decisions/{t['uid']}/reject", json={"decision": "Not needed", "resolved_by": "a"}).json()
    assert r["status"] == "rejected" and r["content"]["rationale"] == "Not needed"


def test_resolve_records_decision_rationale_link_and_resolver(client):
    t = make_tbd(client)
    d = client.post("/decisions", json={"title": "ADR"}).json()
    r = client.post(f"/decisions/{t['uid']}/accept", json={
        "decision": "Use MQTT", "rationale": "Broker already deployed", "linked_decision": d["uid"], "resolved_by": "alice"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["status"] == "accepted" and got["content"]["resolution"] == "Use MQTT"
    assert got["content"]["rationale"] == "Broker already deployed"
    assert got["resolved_by"] == "alice" and got["resolved_at"] and got["resolution_ref"] == d["uid"]


def test_resolve_accepts_legacy_resolution_field_and_rejects_bad_link(client):
    t = make_tbd(client)
    assert client.post(f"/tbds/{t['uid']}/resolve", json={"resolution": "x", "linked_decision": "nope"}).status_code == 422
    assert client.post(f"/tbds/{t['uid']}/resolve", json={"resolution": "x", "resolved_by": "a"}).status_code == 200


def test_resolver_is_the_logged_in_user(repo_root):
    from fastapi.testclient import TestClient
    from reqtool.api import create_app
    from reqtool.auth import UserStore
    UserStore(repo_root).create_user("ed", "correct-horse-battery", role="editor")
    c = TestClient(create_app(repo_root, auth_mode="required"))
    tok = c.post("/auth/login", json={"username": "ed", "password": "correct-horse-battery"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    t = c.post("/tbds", json={"title": "q"}, headers=h).json()
    r = c.post(f"/tbds/{t['uid']}/resolve", json={"decision": "yes", "resolved_by": "someone_else"}, headers=h)
    assert r.json()["resolved_by"] == "ed"


def _link_tbd(client, req_uid, tbd_uid):
    client.put(f"/requirements/{req_uid}", json={"links": [{"type": "tbd", "ref": tbd_uid, "system": "reqtool"}]})


def test_pending_decision_blocks_approval_only_when_policy_is_on(client, repo_root):
    t = make_tbd(client); req = make_req(client, title="R")
    _link_tbd(client, req["uid"], t["uid"])
    review_first(client, req["uid"])
    assert client.post(f"/requirements/{req['uid']}/approve", json={"approved_by": "a"}).status_code in (200, 409)
    store = client.app.state.store if hasattr(client.app.state, "store") else None
    cfg = client.get("/config").json()
    cfg["validation"]["block_approval_on_pending_decisions"] = True
    assert client.put("/config", json=cfg).status_code == 200
    req2 = make_req(client, title="R2"); _link_tbd(client, req2["uid"], t["uid"]); review_first(client, req2["uid"])
    r = client.post(f"/requirements/{req2['uid']}/approve", json={"approved_by": "a"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "pending_decision"
    client.post(f"/decisions/{t['uid']}/accept", json={"decision": "done", "resolved_by": "a"})
    assert client.post(f"/requirements/{req2['uid']}/approve", json={"approved_by": "a"}).status_code == 200


def test_formal_workflow_cannot_skip_review(client):
    wf = client.get("/hierarchy").json()["workflows"]
    for name in ("formal", "safety_formal"):
        assert "approved" not in wf[name]["transitions"]["draft"], name


@pytest.mark.parametrize("typ", ["theme", "initiative", "feature"])
def test_strategic_types_get_readiness_and_done_checklists(client, typ):
    h = client.get("/hierarchy").json()
    assert h["dor"][typ] and h["dod"][typ]
    created = client.post("/requirements", json={"title": "S", "req_type": typ}).json()
    assert [i["item"] for i in created["dor_checklist"]] == [i["item"] for i in h["dor"][typ]]
    assert any(i.get("advisory") for i in created["dor_checklist"] + created["dod_checklist"])


def test_systems_types_have_definition_of_done(client):
    h = client.get("/hierarchy").json()
    for typ in ("performance", "security", "interface", "compliance", "constraint", "operational", "physical"):
        assert h["dod"].get(typ), typ


def test_strategic_fields_are_served_persist_and_export(client):
    h = client.get("/hierarchy").json()
    keys = [f["key"] for f in h["type_fields"]["initiative"]]
    assert {"outcome", "success_measures", "time_horizon", "target_release", "business_value", "risks"} <= set(keys)
    assert h["type_fields"]["theme"] == h["type_fields"]["initiative"]
    u = client.post("/requirements", json={"title": "Init", "req_type": "initiative"}).json()["uid"]
    fields = {"outcome": "Halve onboarding time", "success_measures": ["NPS > 40"], "time_horizon": "next"}
    assert client.put(f"/requirements/{u}", json={"custom_fields": fields}).status_code == 200
    assert client.get(f"/requirements/{u}").json()["custom_fields"] == fields
    from reqtool.exports import _req_to_markdown
    md = _req_to_markdown(client.get(f"/requirements/{u}").json())
    assert "Halve onboarding time" in md and "NPS > 40" in md


def test_decision_edits_reach_memory_after_incremental_reload(repo_root):
    from reqtool.fileio import load_yaml, save_yaml
    store = Store(repo_root); store.load()
    d = store.create_decision({"title": "A"})
    path = store.decision_path(d["uid"])
    data = load_yaml(path); data["title"] = "B"; data["last_modified"] = "2999-01-01T00:00:00Z"
    save_yaml(path, data)
    store.reload_file(path)
    assert store.decisions[d["uid"]]["title"] == "B"
    path.unlink()
    store.reload_file(path)
    assert d["uid"] not in store.decisions


# --- #371: migration of old TBDs, and requirements that refer to an accepted decision --------------------------

def _legacy_tbd(store, **fields):
    """An old-style record as written before #371: ``type: tbd`` with a TBD status."""
    t = store.create_decision({"title": fields.pop("title", "Q")})
    store.update_decision(t["uid"], {"type": "tbd", "id": fields.get("id", "TBD-001"),
                                     "status": fields.get("status", "open"),
                                     "resolution_ref": fields.get("resolution_ref")})
    return t["uid"]


def test_migration_converts_tbds_keeps_aliases_and_is_idempotent(repo_root):
    store = Store(repo_root); store.load()
    open_uid = _legacy_tbd(store, id="TBD-001", status="in_progress")
    adr = store.create_decision({"id": "DEC-004", "title": "MQTT topics"})
    merged_uid = _legacy_tbd(store, id="TBD-002", status="resolved", resolution_ref=adr["uid"])
    req = store.create_requirement({"title": "R", "content": {"description": "Topics: [TBD-002]. Size: [TBD-001]."},
                                    "links": [{"type": "tbd", "ref": merged_uid, "system": "reqtool"}]})

    first = migrate_decisions(repo_root)
    assert first == {"converted": 1, "merged": 1, "links": 1}
    assert migrate_decisions(repo_root) == {"converted": 0, "merged": 0, "links": 0}

    store.load()
    converted = store.decisions[open_uid]
    assert converted["type"] == "decision" and converted["status"] == "proposed" and converted["in_progress"]
    assert converted["id"] == "DEC-005" and converted["aliases"] == ["TBD-001"]
    assert store.decisions[merged_uid]["deleted"]
    assert store.decisions[adr["uid"]]["aliases"] == ["TBD-002"]
    link = store.requirements[req["uid"]]["links"][0]
    assert link == {"type": "decision", "ref": adr["uid"], "system": "reqtool"}
    # Old markers in the text still resolve through the aliases.
    assert store.decision_markers(store.requirements[req["uid"]]) == {open_uid, adr["uid"]}
    assert store.resolve_decision("TBD-001") == open_uid
    assert not [w for w in validate_all(store)["warnings"] if w["code"] == "legacy_tbd"]


def test_accepting_a_decision_asks_referring_requirements_to_check_their_wording(client):
    t = make_tbd(client)
    t = client.put(f"/decisions/{t['uid']}", json={"id": "DEC-090"}).json()
    req = client.post("/requirements", json={"title": "Unit cost", "owner": "bob",
                                             "content": {"description": "Cost shall meet [DEC-090]."}}).json()
    assert not [f for f in client.get(f"/requirements/{req['uid']}/quality").json()["findings"] if f["code"] == "Q007"]

    client.post(f"/decisions/{t['uid']}/accept", json={"decision": "17 GBP at 10 000 units", "resolved_by": "alice"})
    notes = [f for f in client.get(f"/requirements/{req['uid']}/quality").json()["findings"] if f["code"] == "Q007"]
    assert len(notes) == 1 and notes[0]["decision_id"] == "DEC-090" and notes[0]["decision_text"].startswith("17 GBP")
    inbox = client.get("/notifications", params={"user": "bob"}).json()
    assert any(i["event"] == "decision_accepted" and i["uid"] == req["uid"] for i in inbox)

    r = client.post(f"/requirements/{req['uid']}/decision-wording", json={"decision": "DEC-090", "by": "bob"})
    assert r.status_code == 200 and t["uid"] in r.json()["decision_wording_checked"]
    assert r.json()["content"]["description"] == "Cost shall meet [DEC-090]."   # the text is never changed for you
    assert not [f for f in client.get(f"/requirements/{req['uid']}/quality").json()["findings"] if f["code"] == "Q007"]
