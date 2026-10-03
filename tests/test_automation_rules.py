"""UI-12: one automation rule schema, validated on save, with a published list of events/actions."""
from tests.conftest import make_req
from reqtool.automation import AutomationEngine


RULE = {"name": "Tag safety", "event": "requirement_created", "condition": {"req_type": "safety"},
        "action": "add_tag", "target_value": "ASIL-D"}


def test_schema_lists_events_and_actions(client):
    body = client.get("/automation/schema").json()
    assert {"requirement_created", "requirement_approved"} <= {e["id"] for e in body["events"]}
    actions = {a["id"]: a["requires"] for a in body["actions"]}
    assert actions["set_field"] == ["target_field", "target_value"]
    assert actions["add_tag"] == ["target_value"]


def test_seeded_rules_match_the_schema(client):
    rules = client.get("/automation/rules").json()
    assert rules and client.put("/automation/rules", json=rules).status_code == 200


def test_create_save_reload(client):
    r = client.put("/automation/rules", json=[RULE])
    assert r.status_code == 200 and r.json() == {"saved": 1}
    rules = client.get("/automation/rules").json()
    assert len(rules) == 1 and rules[0]["id"].startswith("rule-")
    assert rules[0]["event"] == "requirement_created" and rules[0]["enabled"] is True


def test_legacy_panel_format_is_rejected_with_rule_index(client):
    legacy = {"name": "old", "enabled": True, "event": "requirement.created",
              "actions": [{"type": "set_field", "field": "status", "value": "draft"}]}
    r = client.put("/automation/rules", json=[RULE, legacy])
    assert r.status_code == 422
    assert all(d["loc"][1] == 1 for d in r.json()["detail"])


def test_wrapped_object_body_is_rejected(client):
    assert client.put("/automation/rules", json={"rules": [RULE]}).status_code == 422


def test_action_requirements_and_unknown_values(client):
    bad = [
        {**RULE, "action": "set_field", "target_value": "x"},          # missing target_field
        {**RULE, "action": "explode"},
        {**RULE, "event": "nope"},
        {**RULE, "name": ""},
    ]
    r = client.put("/automation/rules", json=bad)
    assert r.status_code == 422
    assert {d["loc"][1] for d in r.json()["detail"]} == {0, 1, 2, 3}


def test_duplicate_ids_rejected(client):
    r = client.put("/automation/rules", json=[{**RULE, "id": "a"}, {**RULE, "id": "a"}])
    assert r.status_code == 422


def test_engine_actions_are_idempotent(client):
    client.put("/automation/rules", json=[
        RULE,
        {"name": "Assign", "event": "requirement_created", "action": "set_field",
         "target_field": "owner", "target_value": "qa_lead"},
    ])
    store = client.app.state.store
    req = make_req(client, title="S", req_type="safety")  # create event runs both rules
    got = store.get_requirement(req["uid"])
    assert "ASIL-D" in got["tags"] and got["owner"] == "qa_lead"
    # running the same event again changes nothing
    again = AutomationEngine(store.root).execute_event_rules(
        store, "requirement_created", {"uid": req["uid"], "req_type": "safety"})
    assert again == []
    assert store.get_requirement(req["uid"])["tags"].count("ASIL-D") == 1


# ---------------------------------------------------------------------------
# INT-02: rules run when events are published
# ---------------------------------------------------------------------------

def test_approve_runs_matching_rule_once(client):
    client.put("/automation/rules", json=[
        {"name": "QA on approval", "event": "requirement_approved", "condition": {"status": "approved"},
         "action": "set_field", "target_field": "owner", "target_value": "qa_lead"}])
    uid = make_req(client)["uid"]
    r = client.post(f"/requirements/{uid}/approve", json={"approved_by": "alice"})
    assert r.status_code == 200
    got = client.get(f"/requirements/{uid}").json()
    assert got["owner"] == "qa_lead"
    summaries = [h["summary"] for h in got["history"] if "Automation rule" in h["summary"]]
    assert len(summaries) == 1


def test_create_event_applies_tag_for_matching_type_only(client):
    client.put("/automation/rules", json=[RULE])
    safe = make_req(client, title="S", req_type="safety")
    plain = make_req(client, title="P")
    assert "ASIL-D" in client.get(f"/requirements/{safe['uid']}").json().get("tags", [])
    assert "ASIL-D" not in client.get(f"/requirements/{plain['uid']}").json().get("tags", [])


def test_disabled_rule_and_other_events_do_nothing(client):
    client.put("/automation/rules", json=[{**RULE, "enabled": False}])
    r = make_req(client, title="S", req_type="safety")
    assert "ASIL-D" not in client.get(f"/requirements/{r['uid']}").json().get("tags", [])
    client.put("/automation/rules", json=[{**RULE, "event": "requirement_updated"}])
    r2 = make_req(client, title="S2", req_type="safety")
    assert "ASIL-D" not in client.get(f"/requirements/{r2['uid']}").json().get("tags", [])
    client.put(f"/requirements/{r2['uid']}", json={"title": "edited"})
    assert "ASIL-D" in client.get(f"/requirements/{r2['uid']}").json().get("tags", [])


def test_rule_actions_do_not_retrigger_rules(client):
    # an update rule that sets a field must not loop through the update event
    client.put("/automation/rules", json=[
        {"name": "loop?", "event": "requirement_updated", "action": "set_field",
         "target_field": "owner", "target_value": "bot"}])
    uid = make_req(client)["uid"]
    client.put(f"/requirements/{uid}", json={"title": "x"})
    got = client.get(f"/requirements/{uid}").json()
    assert got["owner"] == "bot"
    assert len([h for h in got["history"] if "Automation rule" in h["summary"]]) == 1
