"""MOD-06: cancelled is reachable; workflow definitions are checked for coherence."""
from tests.conftest import make_req
from reqtool.models import HierarchyConfig, HierarchyWorkflowDef, HierarchyWorkflowState as S
from reqtool.validation import check_workflow_graph, validate_all


def _wf(states, transitions, initial="a"):
    return HierarchyConfig(workflows={"w": HierarchyWorkflowDef(
        initial=initial, states=[S(id=i, label=i, terminal=t) for i, t in states], transitions=transitions)})


def test_shipped_workflows_are_coherent(store):
    assert check_workflow_graph(store.hierarchy) == []


def test_story_can_be_cancelled_from_every_open_state(client):
    for start in ("backlog", "ready", "in_progress", "in_review"):
        s = make_req(client, title="S", req_type="story")
        client.app.state.store.requirements[s["uid"]]["status"] = start
        r = client.post(f"/requirements/{s['uid']}/transition", json={"to_state": "cancelled"})
        assert r.status_code == 200, (start, r.text)


def test_detects_unreachable_state():
    h = _wf([("a", False), ("b", True), ("c", True)], {"a": ["b"]})
    assert [p[0] for p in check_workflow_graph(h)] == ["workflow_unreachable_state"]


def test_detects_dead_end_and_unknown_state():
    h = _wf([("a", False), ("b", False), ("done", True)], {"a": ["b", "done"], "b": ["a", "zzz"]})
    codes = {p[0] for p in check_workflow_graph(h)}
    assert codes == {"workflow_unknown_state"}  # b reaches done through a
    h = _wf([("a", False), ("b", False), ("done", True)], {"a": ["b"], "b": ["a"]})
    assert "workflow_dead_end" in {p[0] for p in check_workflow_graph(h)}


def test_validate_all_reports_workflow_problems(store):
    store.hierarchy.workflows["bad"] = HierarchyWorkflowDef(
        initial="a", states=[S(id="a", label="a"), S(id="x", label="x", terminal=True)], transitions={})
    assert any(w["code"] == "workflow_unreachable_state" for w in validate_all(store)["warnings"])
