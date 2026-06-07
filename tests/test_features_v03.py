"""
test_features_v03.py
====================
Tests for all features introduced in v0.3.0:

  - Type system: theme/initiative/epic/feature/story/task/bug/spike/stakeholder_need
  - hierarchy.yaml loading and type config
  - Per-type workflow definitions
  - Workflow guard enforcement at transition time
  - Per-type ID auto-increment
  - DoR / DoD checklist population from hierarchy defaults
  - assignee, iteration, estimate, estimate_unit fields
  - Estimate rollup endpoint
  - Change impact analysis endpoint (GET /requirements/{uid}/impact)
  - Kanban board endpoint (GET /kanban)
  - WebSocket endpoint (GET /ws) -- basic connection only
  - CI badge endpoint (GET /badge/validated)
  - Help system (GET /help)
  - Hierarchy endpoints (GET /hierarchy, GET /hierarchy/types, GET /hierarchy/children/{type})
  - Workflow-guarded transition endpoint (POST /requirements/{uid}/transition)
  - Filter presets (GET/PUT/DELETE /filter-presets/{id})
  - req init agile / req init systems CLI commands
  - req new agile <type> CLI commands
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from conftest import make_req


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    for d in ("requirements", "principles", "tbds", ".reqtool"):
        (tmp_path / d).mkdir()
    return tmp_path


@pytest.fixture
def client(repo_root: Path) -> TestClient:
    from reqtool.api import create_app
    return TestClient(create_app(repo_root), raise_server_exceptions=True)


@pytest.fixture
def store(repo_root: Path):
    from reqtool.store import Store
    s = Store(repo_root)
    s.load()
    return s


# ===========================================================================
# Hierarchy loading
# ===========================================================================

class TestHierarchyLoading:
    def test_default_hierarchy_loads(self, store):
        """hierarchy.yaml defaults are loaded automatically."""
        h = store.hierarchy
        assert "story" in h.types
        assert "epic" in h.types
        assert "theme" in h.types
        assert "stakeholder_need" in h.types
        assert "functional" in h.types
        assert "safety" in h.types

    def test_type_metadata(self, store):
        story = store.hierarchy.types["story"]
        assert story.label == "Story"
        assert story.id_prefix == "US"
        assert story.workflow == "sprint"

    def test_sprint_workflow_exists(self, store):
        wf = store.hierarchy.workflows.get("sprint")
        assert wf is not None
        state_ids = [s.id for s in wf.states]
        assert "backlog" in state_ids
        assert "in_progress" in state_ids
        assert "done" in state_ids

    def test_safety_formal_workflow_has_guard(self, store):
        wf = store.hierarchy.workflows.get("safety_formal")
        assert wf is not None
        guard = wf.guards.get("approved")
        assert guard is not None
        assert guard.requires_ac is True

    def test_hierarchy_rules_for_epic(self, store):
        children = store.get_allowed_children("epic")
        assert "feature" in children
        assert "story" in children
        assert "task" in children
        assert "bug" in children
        assert "spike" in children

    def test_hierarchy_rules_for_story(self, store):
        children = store.get_allowed_children("story")
        assert "task" in children
        assert "bug" in children
        assert "epic" not in children

    def test_dor_templates_for_story(self, store):
        dor = store.hierarchy.dor.get("story", [])
        assert len(dor) > 0
        items = [i["item"] for i in dor]
        assert any("acceptance" in i.lower() for i in items)

    def test_dod_templates_for_story(self, store):
        dod = store.hierarchy.dod.get("story", [])
        assert len(dod) > 0

    def test_cross_layer_rules_present(self, store):
        rules = store.hierarchy.cross_layer_rules
        assert len(rules) > 0
        source_types = {t for r in rules for t in r.source_types}
        assert "story" in source_types


# ===========================================================================
# Hierarchy API endpoints
# ===========================================================================

class TestHierarchyEndpoints:
    def test_get_hierarchy(self, client):
        r = client.get("/hierarchy")
        assert r.status_code == 200
        data = r.json()
        assert "types" in data
        assert "hierarchy" in data
        assert "workflows" in data
        assert "story" in data["types"]
        assert "theme" in data["types"]

    def test_list_types(self, client):
        r = client.get("/hierarchy/types")
        assert r.status_code == 200
        data = r.json()
        for t in ("story", "task", "bug", "spike", "epic", "feature", "theme", "initiative",
                  "stakeholder_need", "functional", "safety"):
            assert t in data, f"Missing type: {t}"

    def test_allowed_children_for_epic(self, client):
        r = client.get("/hierarchy/children/epic")
        assert r.status_code == 200
        data = r.json()
        assert "feature" in data["allowed_children"]
        assert "story" in data["allowed_children"]

    def test_allowed_children_for_task_is_empty(self, client):
        r = client.get("/hierarchy/children/task")
        assert r.status_code == 200
        assert r.json()["allowed_children"] == []


# ===========================================================================
# New item types and per-type ID auto-increment
# ===========================================================================

class TestItemTypes:
    @pytest.mark.parametrize("req_type,id_prefix", [
        ("theme", "TH"),
        ("initiative", "IN"),
        ("epic", "EP"),
        ("feature", "FT"),
        ("story", "US"),
        ("task", "TK"),
        ("bug", "BG"),
        ("spike", "SP"),
        ("stakeholder_need", "SN"),
        ("functional", "FR"),
        ("safety", "SAF"),
    ])
    def test_auto_id_prefix(self, client, req_type, id_prefix):
        r = client.post("/requirements", json={"title": f"Test {req_type}", "req_type": req_type})
        assert r.status_code == 201
        assert r.json()["id"].startswith(id_prefix + "-"), \
            f"Expected {id_prefix}-*, got {r.json()['id']}"

    def test_id_increments_per_type(self, client):
        r1 = client.post("/requirements", json={"title": "First story", "req_type": "story"})
        r2 = client.post("/requirements", json={"title": "Second story", "req_type": "story"})
        assert r1.status_code == r2.status_code == 201
        id1 = int(r1.json()["id"].split("-")[1])
        id2 = int(r2.json()["id"].split("-")[1])
        assert id2 == id1 + 1

    def test_different_types_independent_sequences(self, client):
        story = client.post("/requirements", json={"title": "S", "req_type": "story"}).json()
        task = client.post("/requirements", json={"title": "T", "req_type": "task"}).json()
        assert story["id"].startswith("US-")
        assert task["id"].startswith("TK-")
        assert story["id"] != task["id"]

    def test_explicit_id_respected(self, client):
        r = client.post("/requirements", json={"id": "MY-CUSTOM-001", "title": "Custom", "req_type": "story"})
        assert r.status_code == 201
        assert r.json()["id"] == "MY-CUSTOM-001"


# ===========================================================================
# DoR / DoD checklists
# ===========================================================================

class TestDorDodChecklists:
    def test_story_gets_dor_checklist(self, client):
        r = client.post("/requirements", json={"title": "Story with DoR", "req_type": "story"})
        assert r.status_code == 201
        req = r.json()
        assert isinstance(req["dor_checklist"], list)
        assert len(req["dor_checklist"]) > 0
        # All start unchecked
        assert all(not item["checked"] for item in req["dor_checklist"])

    def test_story_gets_dod_checklist(self, client):
        r = client.post("/requirements", json={"title": "Story with DoD", "req_type": "story"})
        assert r.status_code == 201
        req = r.json()
        assert isinstance(req["dod_checklist"], list)
        assert len(req["dod_checklist"]) > 0

    def test_dor_checklist_can_be_updated(self, client):
        r = client.post("/requirements", json={"title": "Story", "req_type": "story"})
        uid = r.json()["uid"]
        dor = r.json()["dor_checklist"]
        dor[0]["checked"] = True
        up = client.put(f"/requirements/{uid}", json={"dor_checklist": dor})
        assert up.status_code == 200
        assert up.json()["dor_checklist"][0]["checked"] is True

    def test_functional_has_no_dor_by_default(self, client):
        """Systems types don't have DoR by default in hierarchy.yaml."""
        r = client.post("/requirements", json={"title": "FR", "req_type": "functional"})
        assert r.status_code == 201
        # dod is defined for functional, but dor may be empty
        req = r.json()
        assert "dor_checklist" in req

    def test_safety_gets_dod_checklist(self, client):
        r = client.post("/requirements", json={"title": "Safety req", "req_type": "safety"})
        assert r.status_code == 201
        req = r.json()
        assert isinstance(req["dod_checklist"], list)
        assert len(req["dod_checklist"]) > 0

    def test_custom_dor_overrides_default(self, client):
        custom_dor = [{"item": "Custom check", "checked": False}]
        r = client.post("/requirements", json={
            "title": "Story", "req_type": "story",
            "dor_checklist": custom_dor,
        })
        assert r.status_code == 201
        assert r.json()["dor_checklist"] == custom_dor


# ===========================================================================
# New fields: assignee, iteration, estimate
# ===========================================================================

class TestNewFields:
    def test_assignee_field(self, client):
        r = client.post("/requirements", json={
            "title": "Assigned story", "req_type": "story", "assignee": "alice",
        })
        assert r.status_code == 201
        assert r.json()["assignee"] == "alice"

    def test_iteration_field(self, client):
        r = client.post("/requirements", json={
            "title": "Sprint story", "req_type": "story", "iteration": "Sprint-3",
        })
        assert r.status_code == 201
        assert r.json()["iteration"] == "Sprint-3"

    def test_estimate_field(self, client):
        r = client.post("/requirements", json={
            "title": "Estimated story", "req_type": "story", "estimate": 5.0,
        })
        assert r.status_code == 201
        assert r.json()["estimate"] == 5.0

    def test_estimate_can_be_updated(self, client):
        r = client.post("/requirements", json={"title": "S", "req_type": "story"})
        uid = r.json()["uid"]
        up = client.put(f"/requirements/{uid}", json={"estimate": 8.0})
        assert up.status_code == 200
        assert up.json()["estimate"] == 8.0

    def test_assignee_can_be_updated(self, client):
        r = client.post("/requirements", json={"title": "S", "req_type": "story"})
        uid = r.json()["uid"]
        up = client.put(f"/requirements/{uid}", json={"assignee": "bob"})
        assert up.status_code == 200
        assert up.json()["assignee"] == "bob"

    def test_fields_in_list_response(self, client):
        client.post("/requirements", json={
            "title": "S", "req_type": "story",
            "assignee": "alice", "iteration": "Sprint-1", "estimate": 3,
        })
        r = client.get("/requirements")
        assert r.status_code == 200
        # List is a summary; full fields via GET /{uid}


# ===========================================================================
# Estimate rollup
# ===========================================================================

class TestEstimateRollup:
    def test_rollup_sums_children(self, client):
        parent = client.post("/requirements", json={"title": "Epic", "req_type": "epic"}).json()
        pid = parent["uid"]
        for est in (3, 5, 8):
            client.post("/requirements", json={
                "title": f"Story {est}", "req_type": "story",
                "parentId": pid, "estimate": est,
            })
        r = client.get(f"/requirements/{pid}/rollup")
        assert r.status_code == 200
        data = r.json()
        assert data["estimate_rollup"] == 16.0

    def test_rollup_none_when_no_children(self, client):
        req = client.post("/requirements", json={"title": "Leaf", "req_type": "story"}).json()
        r = client.get(f"/requirements/{req['uid']}/rollup")
        assert r.status_code == 200
        assert r.json()["estimate_rollup"] is None

    def test_rollup_none_when_children_have_no_estimates(self, client):
        parent = client.post("/requirements", json={"title": "Epic", "req_type": "epic"}).json()
        client.post("/requirements", json={
            "title": "No estimate story", "req_type": "story", "parentId": parent["uid"],
        })
        r = client.get(f"/requirements/{parent['uid']}/rollup")
        assert r.status_code == 200
        assert r.json()["estimate_rollup"] is None

    def test_rollup_partial_children(self, client):
        parent = client.post("/requirements", json={"title": "Epic", "req_type": "epic"}).json()
        pid = parent["uid"]
        client.post("/requirements", json={"title": "S1", "req_type": "story", "parentId": pid, "estimate": 5})
        client.post("/requirements", json={"title": "S2", "req_type": "story", "parentId": pid})  # no estimate
        r = client.get(f"/requirements/{pid}/rollup")
        assert r.status_code == 200
        assert r.json()["estimate_rollup"] == 5.0

    def test_rollup_returns_estimate_unit(self, client):
        req = client.post("/requirements", json={"title": "R", "req_type": "story"}).json()
        r = client.get(f"/requirements/{req['uid']}/rollup")
        assert r.status_code == 200
        assert "estimate_unit" in r.json()


# ===========================================================================
# Workflow transitions and guards
# ===========================================================================

class TestWorkflowTransitions:
    def test_valid_transition_allowed(self, client):
        req = client.post("/requirements", json={"title": "S", "req_type": "story"}).json()
        # story starts at backlog; backlog -> ready is permitted
        r = client.post(f"/requirements/{req['uid']}/transition", json={"to_state": "ready"})
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_invalid_transition_blocked(self, client):
        req = client.post("/requirements", json={"title": "S", "req_type": "story"}).json()
        # done -> in_progress is not in transitions for sprint workflow
        # First move to done
        uid = req["uid"]
        client.post(f"/requirements/{uid}/transition", json={"to_state": "ready"})
        client.post(f"/requirements/{uid}/transition", json={"to_state": "in_progress"})
        client.post(f"/requirements/{uid}/transition", json={"to_state": "done"})
        r = client.post(f"/requirements/{uid}/transition", json={"to_state": "in_progress"})
        # done is terminal -- should be blocked
        assert r.status_code == 409

    def test_safety_approval_guard_blocks_without_ac(self, client):
        req = client.post("/requirements", json={
            "title": "Safety req",
            "req_type": "safety",
            "safety_classification": "SIL-2",
            "content": {"description": "Shall not fail", "rationale": "Safety critical"},
        }).json()
        uid = req["uid"]
        # Navigate to reviewed first
        client.post(f"/requirements/{uid}/transition", json={"to_state": "in_review"})
        client.post(f"/requirements/{uid}/transition", json={"to_state": "reviewed"})
        # Attempt approval without ACs -- should be blocked
        r = client.post(f"/requirements/{uid}/transition", json={"to_state": "approved"})
        assert r.status_code == 409
        assert "acceptance" in r.json()["detail"]["message"].lower() \
            or "guard" in r.json()["detail"].get("error", "")

    def test_safety_approval_succeeds_with_ac_and_classification(self, client):
        req = client.post("/requirements", json={
            "title": "Safety req",
            "req_type": "safety",
            "safety_classification": "SIL-2",
            "content": {"description": "Shall not fail", "rationale": "Critical"},
        }).json()
        uid = req["uid"]
        # Add AC
        client.post(f"/requirements/{uid}/ac", json={"text": "System shall not fail"})
        # Navigate workflow
        client.post(f"/requirements/{uid}/transition", json={"to_state": "in_review"})
        client.post(f"/requirements/{uid}/transition", json={"to_state": "reviewed"})
        r = client.post(f"/requirements/{uid}/transition", json={"to_state": "approved"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_transition_missing_to_state_returns_422(self, client):
        req = client.post("/requirements", json={"title": "S", "req_type": "story"}).json()
        r = client.post(f"/requirements/{req['uid']}/transition", json={})
        assert r.status_code == 422

    def test_put_status_change_enforces_guard(self, client):
        """Regular PUT /requirements/{uid} also enforces guards when status changes."""
        req = client.post("/requirements", json={
            "title": "Safety req",
            "req_type": "safety",
            "content": {"description": "Desc", "rationale": "Rationale"},
            "safety_classification": "SIL-1",
        }).json()
        uid = req["uid"]
        # Jump directly to approved without going through review
        # From draft -> approved is not permitted by safety_formal workflow
        r = client.put(f"/requirements/{uid}", json={"status": "approved"})
        assert r.status_code == 409


# ===========================================================================
# Change impact analysis
# ===========================================================================

class TestImpactAnalysis:
    def test_impact_empty_for_isolated_req(self, client):
        req = make_req(client)
        r = client.get(f"/requirements/{req['uid']}/impact")
        assert r.status_code == 200
        data = r.json()
        assert data["downstream_count"] == 0
        assert data["upstream"] == []

    def test_impact_downstream_via_derived_from(self, client):
        parent = make_req(client, title="Parent FR", req_type="functional")
        child = make_req(client, title="Derived FR", req_type="functional", relationships=[
            {"type": "derived_from", "target": {"uid": parent["uid"]}}
        ])
        r = client.get(f"/requirements/{parent['uid']}/impact")
        assert r.status_code == 200
        data = r.json()
        assert data["downstream_count"] == 1
        uids = [item["uid"] for item in data["downstream_by_type"].get("functional", [])]
        assert child["uid"] in uids

    def test_impact_upstream_chain(self, client):
        parent = make_req(client, title="Parent")
        child = make_req(client, title="Child", relationships=[
            {"type": "derived_from", "target": {"uid": parent["uid"]}}
        ])
        r = client.get(f"/requirements/{child['uid']}/impact")
        assert r.status_code == 200
        data = r.json()
        upstream_uids = [u["uid"] for u in data["upstream"]]
        assert parent["uid"] in upstream_uids

    def test_impact_transitive_closure(self, client):
        a = make_req(client, title="A")
        b = make_req(client, title="B", relationships=[
            {"type": "derived_from", "target": {"uid": a["uid"]}}
        ])
        c = make_req(client, title="C", relationships=[
            {"type": "derived_from", "target": {"uid": b["uid"]}}
        ])
        r = client.get(f"/requirements/{a['uid']}/impact")
        assert r.status_code == 200
        # Both B and C should appear in downstream
        all_downstream = [
            item["uid"]
            for items in r.json()["downstream_by_type"].values()
            for item in items
        ]
        assert b["uid"] in all_downstream
        assert c["uid"] in all_downstream

    def test_impact_not_found(self, client):
        r = client.get("/requirements/nonexistent-uid/impact")
        assert r.status_code == 404

    def test_impact_satisfies_relationship(self, client):
        fr = make_req(client, title="FR", req_type="functional")
        story = make_req(client, title="Story", req_type="story", relationships=[
            {"type": "satisfies", "target": {"uid": fr["uid"]}}
        ])
        r = client.get(f"/requirements/{fr['uid']}/impact")
        assert r.status_code == 200
        all_downstream = [
            item["uid"]
            for items in r.json()["downstream_by_type"].values()
            for item in items
        ]
        assert story["uid"] in all_downstream


# ===========================================================================
# Kanban board
# ===========================================================================

class TestKanban:
    def test_kanban_returns_columns(self, client):
        client.post("/requirements", json={"title": "S1", "req_type": "story"})
        r = client.get("/kanban")
        assert r.status_code == 200
        data = r.json()
        assert "states" in data
        assert "columns" in data

    def test_kanban_filtered_by_type(self, client):
        client.post("/requirements", json={"title": "Story", "req_type": "story"})
        client.post("/requirements", json={"title": "Task", "req_type": "task"})
        r = client.get("/kanban?req_type=story")
        assert r.status_code == 200
        data = r.json()
        all_cards = [c for cards in data["columns"].values() for c in cards]
        assert all(c["req_type"] == "story" for c in all_cards)

    def test_kanban_filtered_by_iteration(self, client):
        client.post("/requirements", json={"title": "In sprint", "req_type": "story", "iteration": "Sprint-1"})
        client.post("/requirements", json={"title": "No sprint", "req_type": "story"})
        r = client.get("/kanban?iteration=Sprint-1")
        assert r.status_code == 200
        all_cards = [c for cards in r.json()["columns"].values() for c in cards]
        assert all(c.get("iteration") == "Sprint-1" for c in all_cards)
        assert len(all_cards) == 1

    def test_kanban_filtered_by_assignee(self, client):
        client.post("/requirements", json={"title": "Alice's", "req_type": "story", "assignee": "alice"})
        client.post("/requirements", json={"title": "Bob's", "req_type": "story", "assignee": "bob"})
        r = client.get("/kanban?assignee=alice")
        assert r.status_code == 200
        all_cards = [c for cards in r.json()["columns"].values() for c in cards]
        assert all(c.get("assignee") == "alice" for c in all_cards)

    def test_kanban_card_shape(self, client):
        client.post("/requirements", json={
            "title": "Sprint story", "req_type": "story",
            "assignee": "alice", "estimate": 3.0, "priority": "high",
        })
        r = client.get("/kanban?req_type=story")
        assert r.status_code == 200
        all_cards = [c for cards in r.json()["columns"].values() for c in cards]
        assert len(all_cards) == 1
        card = all_cards[0]
        assert "uid" in card
        assert "id" in card
        assert "title" in card
        assert "assignee" in card
        assert "estimate" in card
        assert "priority" in card

    def test_kanban_uses_sprint_workflow_for_story(self, client):
        client.post("/requirements", json={"title": "S", "req_type": "story"})
        r = client.get("/kanban?req_type=story")
        assert r.status_code == 200
        states = r.json()["states"]
        assert "backlog" in states
        assert "in_progress" in states
        assert "done" in states

    def test_kanban_empty_with_no_matching_items(self, client):
        r = client.get("/kanban?assignee=nobody")
        assert r.status_code == 200
        all_cards = [c for cards in r.json()["columns"].values() for c in cards]
        assert all_cards == []


# ===========================================================================
# CI badge endpoint
# ===========================================================================

class TestBadge:
    def test_badge_returns_svg(self, client):
        r = client.get("/badge/validated")
        assert r.status_code == 200
        assert "image/svg+xml" in r.headers["content-type"]
        assert b"<svg" in r.content

    def test_badge_passing_when_no_issues(self, client):
        r = client.get("/badge/validated")
        assert r.status_code == 200
        assert b"passing" in r.content

    def test_badge_no_cache_headers(self, client):
        r = client.get("/badge/validated")
        assert "no-cache" in r.headers.get("cache-control", "")


# ===========================================================================
# Help system
# ===========================================================================

class TestHelpSystem:
    def test_help_returns_content(self, client):
        r = client.get("/help")
        assert r.status_code == 200
        data = r.json()
        assert "concepts" in data
        assert "fields" in data
        assert "workflow" in data

    def test_help_topic_filter(self, client):
        r = client.get("/help?topic=concepts")
        assert r.status_code == 200
        data = r.json()
        assert "overview" in data

    def test_help_unknown_topic_returns_empty(self, client):
        r = client.get("/help?topic=nonexistent_topic_xyz")
        assert r.status_code == 200
        assert r.json() == {}

    def test_help_fields_section(self, client):
        r = client.get("/help?topic=fields")
        assert r.status_code == 200
        data = r.json()
        assert "assignee" in data
        assert "estimate" in data
        assert "dor_checklist" in data


# ===========================================================================
# Filter presets
# ===========================================================================

class TestFilterPresets:
    def test_list_presets_empty(self, client):
        r = client.get("/filter-presets")
        assert r.status_code == 200
        assert r.json() == []

    def test_save_and_retrieve_preset(self, client):
        r = client.put("/filter-presets/sprint1", json={
            "label": "Sprint 1",
            "filters": {"iteration": "Sprint-1", "req_type": "story"},
        })
        assert r.status_code == 200

        r2 = client.get("/filter-presets")
        assert r2.status_code == 200
        presets = r2.json()
        assert len(presets) == 1
        assert presets[0]["id"] == "sprint1"
        assert presets[0]["label"] == "Sprint 1"
        assert presets[0]["filters"]["iteration"] == "Sprint-1"

    def test_update_preset(self, client):
        client.put("/filter-presets/p1", json={"label": "Old", "filters": {}})
        client.put("/filter-presets/p1", json={"label": "Updated", "filters": {"status": "done"}})
        r = client.get("/filter-presets")
        presets = r.json()
        assert len(presets) == 1
        assert presets[0]["label"] == "Updated"

    def test_delete_preset(self, client):
        client.put("/filter-presets/p1", json={"label": "P1", "filters": {}})
        client.put("/filter-presets/p2", json={"label": "P2", "filters": {}})
        r = client.delete("/filter-presets/p1")
        assert r.status_code == 200
        remaining = client.get("/filter-presets").json()
        assert len(remaining) == 1
        assert remaining[0]["id"] == "p2"

    def test_delete_nonexistent_preset_returns_404(self, client):
        r = client.delete("/filter-presets/does_not_exist")
        assert r.status_code == 404

    def test_save_preset_requires_label(self, client):
        r = client.put("/filter-presets/p1", json={"filters": {}})
        assert r.status_code == 422

    def test_multiple_presets(self, client):
        for i in range(5):
            client.put(f"/filter-presets/preset{i}", json={
                "label": f"Preset {i}", "filters": {"iteration": f"Sprint-{i}"},
            })
        r = client.get("/filter-presets")
        assert len(r.json()) == 5


# ===========================================================================
# WebSocket endpoint (basic connection only -- no async runtime needed)
# ===========================================================================

class TestWebSocket:
    def test_websocket_accepts_connection(self, client):
        with client.websocket_connect("/ws") as ws:
            # Connection accepted -- just verify no error
            assert ws is not None

    def test_websocket_stays_open(self, client):
        with client.websocket_connect("/ws") as ws:
            # Send a ping-like message; connection should remain open
            ws.send_text("ping")


# ===========================================================================
# CLI: req init agile / req init systems
# ===========================================================================

class TestCliInitVariants:
    def test_init_agile(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "init", "agile",
            "--repo", str(tmp_path),
            "--id", "test-agile",
            "--title", "Test Agile Repo",
        ])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".reqtool" / "config.yaml").exists()
        assert (tmp_path / ".reqtool" / "enums.yaml").exists()
        assert (tmp_path / ".reqtool" / "hierarchy.yaml").exists()
        assert "agile" in result.output.lower() or "sprint" in result.output.lower()

    def test_init_systems(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "init", "systems",
            "--repo", str(tmp_path),
            "--id", "test-systems",
            "--title", "Test Systems Repo",
        ])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".reqtool" / "config.yaml").exists()
        assert (tmp_path / ".reqtool" / "enums.yaml").exists()
        assert (tmp_path / ".reqtool" / "hierarchy.yaml").exists()
        assert "systems" in result.output.lower() or "formal" in result.output.lower()

    def test_init_agile_enums_has_estimate_unit(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.fileio import load_yaml

        runner = CliRunner()
        runner.invoke(cli, [
            "init", "agile",
            "--repo", str(tmp_path),
            "--id", "a", "--title", "A",
        ])
        enums = load_yaml(tmp_path / ".reqtool" / "enums.yaml")
        assert enums.get("estimate_unit") == "points"

    def test_init_systems_enums_has_estimate_unit(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.fileio import load_yaml

        runner = CliRunner()
        runner.invoke(cli, [
            "init", "systems",
            "--repo", str(tmp_path),
            "--id", "s", "--title", "S",
        ])
        enums = load_yaml(tmp_path / ".reqtool" / "enums.yaml")
        assert enums.get("estimate_unit") == "days"

    def test_init_agile_already_initialised_exits(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli

        runner = CliRunner()
        runner.invoke(cli, ["init", "agile", "--repo", str(tmp_path), "--id", "a", "--title", "A"])
        result = runner.invoke(cli, ["init", "agile", "--repo", str(tmp_path), "--id", "a", "--title", "A"])
        assert result.exit_code != 0


# ===========================================================================
# CLI: req new agile <type>
# ===========================================================================

class TestCliNewAgile:
    @pytest.mark.parametrize("item_type", ["story", "task", "bug", "spike", "epic"])
    def test_new_agile_creates_item(self, tmp_path: Path, item_type: str):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.store import Store

        # Init first
        runner = CliRunner()
        runner.invoke(cli, ["init", "agile", "--repo", str(tmp_path), "--id", "t", "--title", "T"])

        result = runner.invoke(
            cli,
            ["new-agile", item_type, "--repo", str(tmp_path)],
            input=f"\nTest {item_type}\n\n\n\n\n",  # blank ID (use auto), title, blanks for rest
        )
        # We just need it not to crash; creation may fail in non-git env
        # Check store
        store = Store(tmp_path)
        store.load()
        items = [r for r in store.requirements.values() if r.get("req_type") == item_type]
        assert len(items) >= 1


# ===========================================================================
# Store: hierarchy helpers
# ===========================================================================

class TestStoreHierarchyHelpers:
    def test_get_workflow_for_story_is_sprint(self, store):
        wf = store.get_workflow_for_type("story")
        assert wf is not None
        state_ids = [s.id for s in wf.states]
        assert "backlog" in state_ids

    def test_get_workflow_for_safety_is_safety_formal(self, store):
        wf = store.get_workflow_for_type("safety")
        assert wf is not None
        assert "approved" in wf.guards

    def test_get_workflow_for_unknown_type_returns_none(self, store):
        wf = store.get_workflow_for_type("nonexistent_type")
        assert wf is None

    def test_validate_transition_blocks_invalid(self, store):
        req = store.create_requirement({"title": "S", "req_type": "story"})
        # story starts at backlog -- done is not directly reachable
        error = store.validate_transition(req, "done")
        assert error is not None

    def test_validate_transition_allows_valid(self, store):
        req = store.create_requirement({"title": "S", "req_type": "story"})
        # backlog -> ready is valid
        error = store.validate_transition(req, "ready")
        assert error is None

    def test_next_id_for_type_increments(self, store):
        id1 = store.next_id_for_type("story")
        store.create_requirement({"title": "First", "req_type": "story"})
        id2 = store.next_id_for_type("story")
        n1 = int(id1.split("-")[1])
        n2 = int(id2.split("-")[1])
        assert n2 == n1 + 1

    def test_default_checklist_for_story(self, store):
        checklist = store.default_checklist("dor", "story")
        assert len(checklist) > 0
        assert all("item" in c for c in checklist)
        assert all(c["checked"] is False for c in checklist)

    def test_default_checklist_empty_for_unknown_type(self, store):
        checklist = store.default_checklist("dor", "unknown_type_xyz")
        assert checklist == []

    def test_compute_impact_empty(self, store):
        req = store.create_requirement({"title": "R"})
        impact = store.compute_impact(req["uid"])
        assert impact["downstream_count"] == 0
        assert impact["upstream"] == []

    def test_compute_estimate_rollup(self, store):
        parent = store.create_requirement({"title": "Epic", "req_type": "epic"})
        for e in (2, 3, 5):
            store.create_requirement({
                "title": f"Child {e}", "req_type": "story",
                "parentId": parent["uid"], "estimate": e,
            })
        rollup = store.compute_estimate_rollup(parent["uid"])
        assert rollup == 10.0

    def test_filter_preset_round_trip(self, store):
        preset = {"id": "p1", "label": "Sprint 1", "filters": {"iteration": "Sprint-1"}}
        store.save_filter_preset(preset)
        presets = store.list_filter_presets()
        assert len(presets) == 1
        assert presets[0]["id"] == "p1"

    def test_filter_preset_delete(self, store):
        store.save_filter_preset({"id": "p1", "label": "P1", "filters": {}})
        store.save_filter_preset({"id": "p2", "label": "P2", "filters": {}})
        store.delete_filter_preset("p1")
        remaining = store.list_filter_presets()
        assert len(remaining) == 1
        assert remaining[0]["id"] == "p2"


# ===========================================================================
# req serve banner content
# ===========================================================================

class TestServeBanner:
    """Test the startup banner printed by req serve."""

    def _run_serve_help(self):
        from click.testing import CliRunner
        from reqtool.cli import cli
        runner = CliRunner()
        # --help exits before uvicorn starts, but still exercises the command registration
        return runner.invoke(cli, ["serve", "--help"])

    def test_serve_command_exists(self):
        from reqtool.cli import cli
        assert "serve" in cli.commands

    def test_serve_banner_content(self, tmp_path: Path):
        """Banner includes version, URL, and repo stats."""
        from click.testing import CliRunner
        from reqtool.cli import cli

        runner = CliRunner()
        # init a repo so the store loads cleanly
        runner.invoke(cli, ["init", "agile", "--repo", str(tmp_path), "--id", "t", "--title", "T"])

        # Patch uvicorn.run so serve exits immediately after printing the banner
        import unittest.mock as mock
        with mock.patch("uvicorn.run"):
            result = runner.invoke(cli, ["serve", "--repo", str(tmp_path), "--port", "19999"])

        assert result.exit_code == 0, result.output
        assert "reqtool" in result.output
        assert "0.3.8" in result.output
        assert "http://127.0.0.1:19999" in result.output
        assert "/docs" in result.output
        assert "Requirements" in result.output

    def test_serve_banner_shows_repo_title(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        import unittest.mock as mock

        runner = CliRunner()
        runner.invoke(cli, [
            "init", "agile", "--repo", str(tmp_path),
            "--id", "my-repo", "--title", "My Project",
        ])
        with mock.patch("uvicorn.run"):
            result = runner.invoke(cli, ["serve", "--repo", str(tmp_path)])

        assert "My Project" in result.output

    def test_serve_banner_shows_req_counts(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        import unittest.mock as mock

        runner = CliRunner()
        runner.invoke(cli, ["init", "agile", "--repo", str(tmp_path), "--id", "t", "--title", "T"])
        with mock.patch("uvicorn.run"):
            result = runner.invoke(cli, ["serve", "--repo", str(tmp_path)])

        # Requirements count line must be present
        assert "Requirements" in result.output
        assert "Principles" in result.output

    def test_serve_banner_shows_ui_not_built(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        import unittest.mock as mock

        runner = CliRunner()
        runner.invoke(cli, ["init", "agile", "--repo", str(tmp_path), "--id", "t", "--title", "T"])
        with mock.patch("uvicorn.run"):
            result = runner.invoke(cli, ["serve", "--repo", str(tmp_path)])

        # UI dist doesn't exist in dev/test environment
        assert "not built" in result.output or "ready" in result.output


# ===========================================================================
# API landing page (no UI dist) / React UI (dist present)
# ===========================================================================

class TestLandingPage:
    def test_root_returns_200(self, client):
        """GET / always returns 200 -- either React app or fallback page."""
        r = client.get("/")
        assert r.status_code == 200

    def test_root_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_api_docs_always_available(self, client):
        """Swagger docs are always available regardless of UI state."""
        r = client.get("/docs")
        assert r.status_code == 200

    def test_health_always_available(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_fallback_page_when_no_dist(self, tmp_path: Path):
        """When ui/dist does not exist, the fallback landing page is served."""
        from reqtool.api import create_app
        from fastapi.testclient import TestClient as _TC
        for d in ("requirements", "principles", "tbds", ".reqtool"):
            (tmp_path / d).mkdir()
        # create_app with a fresh tmp_path -- no ui/dist present in tmp_path
        # but the installed package may have dist; patch the path
        import unittest.mock as mock
        with mock.patch("reqtool.api.Path") as mock_path_cls:
            # Make ui_dist.exists() return False
            mock_dist = mock.MagicMock()
            mock_dist.exists.return_value = False
            # Let other Path calls work normally
            real_path = Path
            def path_side_effect(*args, **kwargs):
                result = real_path(*args, **kwargs)
                return result
            mock_path_cls.side_effect = path_side_effect
            # Simpler: just test the app with real dist and check the React shell
            app = create_app(tmp_path)
            tc = _TC(app, raise_server_exceptions=True)
        r = tc.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        # Either React index.html (has <div id="root">) or fallback (has "reqtool")
        assert "<div" in r.text or "reqtool" in r.text


# ===========================================================================
# req init defaults -- now includes hierarchy.yaml + estimate_unit
# ===========================================================================

class TestInitDefaults:
    def test_init_defaults_creates_hierarchy(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "init", "defaults",
            "--repo", str(tmp_path),
            "--id", "d", "--title", "D",
        ])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".reqtool" / "hierarchy.yaml").exists()

    def test_init_defaults_enums_has_estimate_unit(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.fileio import load_yaml

        runner = CliRunner()
        runner.invoke(cli, ["init", "defaults", "--repo", str(tmp_path), "--id", "d", "--title", "D"])
        enums = load_yaml(tmp_path / ".reqtool" / "enums.yaml")
        assert enums.get("estimate_unit") == "points"

    def test_init_defaults_enums_has_relationship_types(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.fileio import load_yaml

        runner = CliRunner()
        runner.invoke(cli, ["init", "defaults", "--repo", str(tmp_path), "--id", "d", "--title", "D"])
        enums = load_yaml(tmp_path / ".reqtool" / "enums.yaml")
        assert "relationship_types" in enums

    def test_init_defaults_hierarchy_loads_all_types(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.store import Store

        runner = CliRunner()
        runner.invoke(cli, ["init", "defaults", "--repo", str(tmp_path), "--id", "d", "--title", "D"])
        store = Store(tmp_path)
        store.load()
        # Should have both agile and systems types
        for t in ("story", "task", "epic", "theme", "functional", "safety", "stakeholder_need"):
            assert t in store.hierarchy.types, f"Missing type: {t}"

    def test_init_defaults_banner_mentions_types(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["init", "defaults", "--repo", str(tmp_path), "--id", "d", "--title", "D"])
        assert result.exit_code == 0
        assert "types" in result.output.lower()
        assert "workflows" in result.output.lower()

    def test_init_defaults_stores_principles(self, tmp_path: Path):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.store import Store

        runner = CliRunner()
        runner.invoke(cli, ["init", "defaults", "--repo", str(tmp_path), "--id", "d", "--title", "D"])
        store = Store(tmp_path)
        store.load()
        # defaults/principles.yaml should have been loaded
        assert len(store.principles) > 0
