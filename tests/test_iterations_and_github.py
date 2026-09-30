"""
tests/test_iterations_and_github.py
====================================
Unit tests for Iteration/Sprint management engine and GitHub webhook ingestion.
"""

from pathlib import Path
from reqtool.iterations import IterationStore
from reqtool.github_sync import parse_requirement_refs, process_github_push_event


def test_iteration_store_crud(tmp_path: Path):
    store = IterationStore(tmp_path)
    iterations = store.load_iterations()
    assert len(iterations) >= 3

    # Upsert new sprint
    new_it = {
        "id": "sprint-99",
        "title": "Sprint 99 Test",
        "methodology": "scrum",
        "status": "active",
        "capacity_story_points": 35.0,
    }
    store.upsert_iteration(new_it)

    fetched = store.get_iteration("sprint-99")
    assert fetched is not None
    assert fetched["title"] == "Sprint 99 Test"

    # Delete
    assert store.delete_iteration("sprint-99") is True
    assert store.get_iteration("sprint-99") is None


def test_parse_requirement_refs():
    text = "Fixes REQ-SYS-001 and resolves #HW-002: updated sensor driver"
    refs = parse_requirement_refs(text)
    assert "REQ-SYS-001" in refs
    assert "HW-002" in refs


def test_parse_requirement_refs_edge_cases():
    assert parse_requirement_refs("") == []
    assert parse_requirement_refs("No refs here in regular text.") == []
    assert set(parse_requirement_refs("REQ-1 and REQ-1")) == {"REQ-1"}
    assert set(parse_requirement_refs("fixes req-sys-005 and closes #SW-101")) == {"REQ-SYS-005", "SW-101"}


class TestIterationAndGithubApi:
    def test_iterations_api(self, client):
        r = client.get("/iterations")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 3

        # Metrics API
        r_m = client.get("/iterations/sprint-01/metrics")
        assert r_m.status_code == 200
        m = r_m.json()
        assert m["iteration_id"] == "sprint-01"

    def test_github_webhook(self, client):
        payload = {
            "ref": "refs/heads/main",
            "repository": {"full_name": "org/product-dev-repo"},
            "commits": [
                {
                    "id": "abc123456789",
                    "message": "Fixes REQ-SYS-001: Implement thermal control loop",
                    "author": {"username": "dev_lead"},
                }
            ],
        }
        r = client.post("/webhooks/github", json=payload, headers={"X-GitHub-Event": "push"})
        assert r.status_code == 200
        res = r.json()
        assert res["status"] == "ok"
        assert res["event"] == "push"

    def test_github_webhook_empty_commits(self, client):
        payload = {"ref": "refs/heads/main", "commits": []}
        r = client.post("/webhooks/github", json=payload, headers={"X-GitHub-Event": "push"})
        assert r.status_code == 200
        res = r.json()
        assert res["processed_links"] == 0

    def test_github_webhook_non_push_event(self, client):
        payload = {"action": "opened"}
        r = client.post("/webhooks/github", json=payload, headers={"X-GitHub-Event": "issues"})
        assert r.status_code == 200
        res = r.json()
        assert res["processed_links"] == 0
