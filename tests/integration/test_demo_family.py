"""The ``req init demo`` data: a product family that uses every feature, not a thin sample."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.cli import cli
from reqtool.features import visuals
from reqtool.store import Store

DELIVERY = ("theme", "initiative", "epic", "feature", "story", "task", "bug", "spike", "issue")
TRIAGE_OUTCOMES = {"reported", "in_triage", "needs_info", "defect", "fixing", "fixed", "enhancement", "planned",
                   "user_error", "duplicate", "not_reproducible", "closed"}


@pytest.fixture(scope="module")
def root(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("family")
    result = CliRunner().invoke(cli, ["init", "demo", "--repo", str(path)])
    assert result.exit_code == 0, result.output
    return path


@pytest.fixture(scope="module")
def store(root) -> Store:
    s = Store(root)
    s.load()
    return s


@pytest.fixture(scope="module")
def client(root) -> TestClient:
    return TestClient(create_app(root))


def test_it_is_a_family_with_plenty_of_every_kind_of_item(store):
    kinds = Counter(r["req_type"] for r in store.requirement_map().values())
    assert len(store.product_map()) >= 7
    assert kinds["theme"] >= 3 and kinds["initiative"] >= 8 and kinds["epic"] >= 12 and kinds["feature"] >= 8
    assert kinds["story"] >= 60 and kinds["task"] >= 30 and kinds["bug"] >= 5 and kinds["spike"] >= 4 and kinds["issue"] >= 12
    assert sum(n for t, n in kinds.items() if t not in DELIVERY) >= 240
    assert len([d for d in store.decision_map().values() if d.get("type") != "tbd"]) >= 12
    assert len([d for d in store.decision_map().values() if d.get("type") == "tbd"]) >= 12


def test_the_repository_validates_cleanly_with_and_without_the_rules(root):
    for args in (["validate"], ["validate", "--rules"]):
        result = CliRunner().invoke(cli, [*args, "--repo", str(root)])
        assert result.exit_code == 0, result.output
        assert "Errors" not in result.output


def test_every_status_move_is_a_legal_step_and_dates_run_forward(store):
    for r in store.requirement_map().values():
        workflow = store.get_workflow_for_type(r["req_type"])
        current, dates = workflow.initial, [h["date"] for h in r["history"]]
        assert dates == sorted(dates), r["id"]
        for h in r["history"]:
            if h.get("status_to"):
                assert h["status_from"] == current, r["id"]
                assert h["status_to"] in workflow.transitions[current], (r["id"], current, h["status_to"])
                current = h["status_to"]
        assert current == r["status"], r["id"]


def test_issues_cover_every_triage_outcome_and_defects_come_from_issues(store):
    issues = [r for r in store.requirement_map().values() if r["req_type"] == "issue"]
    assert {i["status"] for i in issues} >= TRIAGE_OUTCOMES
    raised = [r for r in store.requirement_map().values()
              if r["req_type"] == "bug" and any(rel["type"] == "derived_from" for rel in r.get("relationships") or [])]
    assert len(raised) >= 3 and all(r.get("parentId") for r in raised)


def test_sprints_gates_and_the_planned_work_line_up(store):
    from reqtool.iterations import IterationStore
    iterations = {i["id"]: i for i in IterationStore(store.root).load_iterations()}
    assert [iterations[f"sprint-0{n}"]["status"] for n in range(1, 6)] == ["completed"] * 3 + ["active", "planned"]
    assert any(i["methodology"] == "waterfall" for i in iterations.values())
    used = {r["iteration"] for r in store.requirement_map().values() if r.get("iteration")}
    assert used and used <= set(iterations)


def test_a_story_was_forced_closed_with_a_reason(store):
    forced = [r for r in store.requirement_map().values() if (r.get("attributes") or {}).get("forced")]
    assert forced and forced[0]["attributes"]["forced"]["reason"]


def test_decisions_have_lineage_and_questions_resolve_into_them(store):
    decisions = store.decision_map()
    assert any(d.get("superseded_by") for d in decisions.values())
    assert any(d.get("resolution_ref") for d in decisions.values() if d.get("type") == "tbd")
    assert {d["status"] for d in decisions.values()} >= {"accepted", "proposed", "rejected", "superseded", "open", "resolved"}


def test_principles_are_placed_and_cited(store):
    heat = visuals.principle_heatmap(store)
    assert heat["principles"] >= 100 and 0 < heat["uncited"] < heat["principles"]
    assert len(heat["areas"]) >= 5


def test_collaboration_data_exists(store, root):
    from reqtool.automation import AutomationEngine
    from reqtool.features import reviews
    assert len(list((root / "comments").glob("*.yaml"))) >= 8
    assert len(reviews.list_requests(store)) >= 8
    assert len(store.list_filter_presets()) >= 4
    assert len(AutomationEngine(root).load_rules(include_defaults=False)) >= 3
    assert any(store.list_attachments(uid) for uid in store.requirement_map())


@pytest.mark.parametrize("path", [
    "/views/hierarchy", "/views/type-structure", "/views/coverage", "/views/flow", "/views/decisions",
    "/views/principles", "/traceability/grid?columns=tests", "/traceability/grid?columns=modules", "/roadmap/board",
    "/kanban", "/iterations",
])
def test_the_views_answer_with_data(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text


def test_the_completed_sprints_burn_up_to_done_and_the_flow_shows_stuck_work(client):
    for n in (1, 2, 3):
        body = client.get(f"/views/burnup/sprint-0{n}").json()
        assert body["items"] >= 5 and body["done"] >= body["scope"] * 0.8
    flow = client.get("/views/flow").json()
    stuck = sum(s["stuck_count"] for w in flow["workflows"] for s in w["states"])
    assert stuck >= 3


def test_each_product_scopes_to_its_own_part_of_the_family(client):
    totals = {p: client.get(f"/views/hierarchy?product={p}").json()["total"]
              for p in ("env-sensor-v1", "thread_gateway", "cloud_platform", "companion_app")}
    assert all(t >= 30 for t in totals.values())
    assert totals["env-sensor-v1"] > totals["thread_gateway"]
