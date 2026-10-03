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


def test_engine_runs_saved_rules_set_field_and_add_tag(client):
    client.put("/automation/rules", json=[
        RULE,
        {"name": "Assign", "event": "requirement_created", "action": "set_field",
         "target_field": "owner", "target_value": "qa_lead"},
    ])
    store = client.app.state.store
    req = make_req(client, title="S", req_type="safety")
    engine = AutomationEngine(store.root)
    done = engine.execute_event_rules(store, "requirement_created", {"uid": req["uid"], "req_type": "safety"})
    assert {d["action"] for d in done} == {"add_tag", "set_field"}
    got = store.get_requirement(req["uid"])
    assert "ASIL-D" in got["tags"] and got["owner"] == "qa_lead"
    # idempotent: tag is not added twice
    again = engine.execute_event_rules(store, "requirement_created", {"uid": req["uid"], "req_type": "safety"})
    assert "add_tag" not in {d["action"] for d in again}
    assert store.get_requirement(req["uid"])["tags"].count("ASIL-D") == 1
