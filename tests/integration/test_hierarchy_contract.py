"""QA-01: the API and the UI must follow ``hierarchy.yaml``, the single source of truth for types and workflows.

These tests are generated from the configuration, so adding a type or a transition to the file is checked
without writing a new test.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import build_agile_repo, make_req

UI_WORKFLOW_JS = Path(__file__).resolve().parents[2] / "src" / "reqtool" / "ui" / "src" / "workflow.js"


@pytest.fixture
def hierarchy(client):
    return client.get("/hierarchy").json()


def test_the_configuration_is_internally_consistent(hierarchy):
    types, rules, workflows = hierarchy["types"], hierarchy["hierarchy"], hierarchy["workflows"]
    for name, cfg in types.items():
        assert cfg["workflow"] in workflows, f"type {name} uses an unknown workflow"
    for parent, rule in rules.items():
        assert parent in types, f"hierarchy rule for unknown type {parent}"
        for child in rule["allowed_children"]:
            assert child in types, f"{parent} allows unknown child type {child}"
    for name, wf in workflows.items():
        states = {s["id"] for s in wf["states"]}
        assert wf["initial"] in states, f"workflow {name}: initial state is not a state"
        for source, targets in wf["transitions"].items():
            assert source in states, f"workflow {name}: transition from unknown state {source}"
            assert set(targets) <= states, f"workflow {name}: {source} leads to an unknown state"
        for state in wf.get("guards", {}):
            assert state in states, f"workflow {name}: guard on unknown state {state}"
    prefixes = [cfg["id_prefix"] for cfg in types.values()]
    assert len(prefixes) == len(set(prefixes)), "two types share an ID prefix"


def test_children_endpoint_serves_the_configured_rule_for_every_type(client, hierarchy):
    for name, rule in hierarchy["hierarchy"].items():
        body = client.get(f"/hierarchy/children/{name}").json()
        assert body["allowed_children"] == rule["allowed_children"], name
    assert client.get("/hierarchy/children/not_a_type").json()["allowed_children"] == []


def test_the_agile_levels_nest_in_the_documented_order(agile_client):
    _, items = agile_client
    by_uid = {i["uid"]: i for i in items.values()}
    types = []
    node = items["task"]
    while node:
        types.append(node["req_type"])
        node = by_uid.get(node.get("parentId"))
    assert types == ["task", "story", "feature", "epic", "initiative", "theme"]


def test_every_allowed_parent_child_pair_can_be_created_when_enforced(client):
    client.app.state.store.hierarchy.enforce = "error"
    rules = client.get("/hierarchy").json()["hierarchy"]
    for parent_type, rule in rules.items():
        for child_type in rule["allowed_children"]:
            parent = make_req(client, req_type=parent_type)
            r = client.post("/requirements", json={"title": "child", "req_type": child_type, "parentId": parent["uid"]})
            assert r.status_code == 201, f"{parent_type} -> {child_type}: {r.text}"


def test_every_disallowed_pair_is_refused_when_enforced(client):
    client.app.state.store.hierarchy.enforce = "error"
    rules = client.get("/hierarchy").json()["hierarchy"]
    for parent_type, rule in rules.items():
        parent = make_req(client, req_type=parent_type)
        for child_type in rules:
            if child_type in rule["allowed_children"]:
                continue
            r = client.post("/requirements", json={"title": "child", "req_type": child_type, "parentId": parent["uid"]})
            assert r.status_code == 409, f"{parent_type} -> {child_type} should be refused"
            assert r.json()["detail"]["error"] == "hierarchy_violation"


def test_warn_mode_accepts_a_disallowed_pair(client):
    client.app.state.store.hierarchy.enforce = "warn"
    parent = make_req(client, req_type="task")
    assert client.post("/requirements", json={"title": "c", "req_type": "theme", "parentId": parent["uid"]}).status_code == 201


def _legal(workflow, source, target):
    return target == source or target in workflow["transitions"].get(source, [])


def test_the_store_allows_exactly_the_configured_transitions(client, hierarchy):
    """Every ordered pair of states, for every type, is allowed if and only if the workflow lists it."""
    store = client.app.state.store
    for type_name, cfg in hierarchy["types"].items():
        workflow = hierarchy["workflows"][cfg["workflow"]]
        states = [s["id"] for s in workflow["states"]]
        for source in states:
            for target in states:
                # No requirements map: the transition rules are under test, not the child or content guards.
                problem = store_transition(store, type_name, source, target)
                if _legal(workflow, source, target):
                    assert problem is None or "permitted" not in problem, (type_name, source, target, problem)
                else:
                    assert problem and "not permitted" in problem, (type_name, source, target)


def store_transition(store, type_name, source, target):
    from reqtool.stores.hierarchy_store import validate_transition
    req = {"req_type": type_name, "status": source}
    return validate_transition(store.hierarchy, store.config.workflow, req, target, requirements=None)


def test_the_api_enforces_the_workflow_on_a_real_item(agile_client):
    client, items = agile_client
    done = items["story_done"]
    assert done["status"] == "done"
    r = client.post(f"/requirements/{done['uid']}/transition", json={"to_state": "backlog"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "workflow_guard"
    new = items["story_new"]
    r = client.post(f"/requirements/{new['uid']}/transition", json={"to_state": "done"})
    assert r.status_code == 409
    assert client.get(f"/requirements/{new['uid']}").json()["status"] == new["status"]


def test_the_agile_fixture_has_items_in_several_states(agile_client):
    _, items = agile_client
    statuses = {i["status"] for i in items.values()}
    assert {"active", "done", "in_progress", "in_review"} <= statuses and len(statuses) >= 5


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_ui_resolves_the_same_workflow_as_the_server(tmp_path, client, hierarchy):
    """workflow.js is what the UI uses to offer transitions: run it against the real /hierarchy and /workflow."""
    from reqtool.stores.hierarchy_store import get_workflow_for_type
    store = client.app.state.store
    shutil.copy(UI_WORKFLOW_JS, tmp_path / "workflow.mjs")
    (tmp_path / "data.json").write_text(json.dumps({
        "hierarchy": hierarchy, "fallback": client.get("/workflow").json(), "types": list(hierarchy["types"]) + ["unknown"],
    }))
    (tmp_path / "run.mjs").write_text(
        "import { resolveWorkflow } from './workflow.mjs';\n"
        "import { readFileSync } from 'node:fs';\n"
        "const d = JSON.parse(readFileSync(new URL('./data.json', import.meta.url)));\n"
        "const out = {};\n"
        "for (const t of d.types) out[t] = resolveWorkflow(t, d.hierarchy, d.fallback);\n"
        "console.log(JSON.stringify(out));\n")
    result = subprocess.run(["node", str(tmp_path / "run.mjs")], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    resolved = json.loads(result.stdout)
    for type_name in hierarchy["types"]:
        server = get_workflow_for_type(store.hierarchy, type_name)
        ui = resolved[type_name]
        assert [s["id"] for s in ui["states"]] == [s.id for s in server.states], type_name
        assert ui["transitions"] == server.transitions, type_name
    # An unknown type falls back to the global workflow, as the server does.
    assert resolved["unknown"]["transitions"] == hierarchy_fallback(client)


def hierarchy_fallback(client):
    return client.get("/workflow").json()["transitions"]


def test_a_new_item_starts_in_its_workflows_initial_state(client, hierarchy):
    for type_name, cfg in hierarchy["types"].items():
        created = make_req(client, req_type=type_name)
        assert created["status"] == hierarchy["workflows"][cfg["workflow"]]["initial"], type_name


def test_build_agile_repo_can_run_twice_in_separate_clients(repo_root):
    from fastapi.testclient import TestClient
    from reqtool.api import create_app
    items = build_agile_repo(TestClient(create_app(repo_root)))
    assert len(items) == 11
