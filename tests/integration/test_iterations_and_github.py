"""
tests/test_iterations_and_github.py
====================================
Unit tests for Iteration/Sprint management engine and GitHub webhook ingestion.
"""

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from reqtool.iterations import IterationStore
from reqtool.github_sync import parse_requirement_refs


GH_SECRET = "s3cret"


@pytest.fixture(autouse=True)
def _gh_secret(monkeypatch):
    monkeypatch.setenv("REQTOOL_GITHUB_WEBHOOK_SECRET", GH_SECRET)


def _signed_post(client, payload, event, secret=GH_SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/github", content=body,
                       headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig,
                                "Content-Type": "application/json"})


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
        r = _signed_post(client, payload, "push")
        assert r.status_code == 200
        res = r.json()
        assert res["status"] == "ok"
        assert res["event"] == "push"

    def test_github_webhook_empty_commits(self, client):
        payload = {"ref": "refs/heads/main", "commits": []}
        r = _signed_post(client, payload, "push")
        assert r.status_code == 200
        res = r.json()
        assert res["processed_links"] == 0

    def test_github_webhook_non_push_event(self, client):
        payload = {"action": "opened"}
        r = _signed_post(client, payload, "issues")
        assert r.status_code == 200
        res = r.json()
        assert res["processed_links"] == 0


class TestGithubSignature:
    """SEC-18: unsigned or wrongly signed payloads never reach the handler."""

    def _raw(self, client, headers):
        return client.post("/webhooks/github", content=b'{"commits": []}',
                           headers={"X-GitHub-Event": "push", "Content-Type": "application/json", **headers})

    def test_missing_signature_401(self, client):
        assert self._raw(client, {}).status_code == 401

    def test_malformed_signature_401(self, client):
        assert self._raw(client, {"X-Hub-Signature-256": "abc"}).status_code == 401
        assert self._raw(client, {"X-Hub-Signature-256": "sha1=" + "0" * 40}).status_code == 401

    def test_wrong_secret_401(self, client):
        assert _signed_post(client, {"commits": []}, "push", secret="other").status_code == 401

    def test_tampered_body_401(self, client):
        body = b'{"commits": []}'
        sig = "sha256=" + hmac.new(GH_SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = client.post("/webhooks/github", content=b'{"commits": [1]}',
                        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
        assert r.status_code == 401

    def test_correct_signature_200(self, client):
        assert _signed_post(client, {"commits": []}, "push").status_code == 200

    def test_disabled_without_secret(self, client, monkeypatch):
        monkeypatch.delenv("REQTOOL_GITHUB_WEBHOOK_SECRET")
        assert _signed_post(client, {"commits": []}, "push").status_code == 503

    def test_reachable_without_login_in_required_mode(self, repo_root, monkeypatch):
        from fastapi.testclient import TestClient
        from reqtool.api import create_app
        c = TestClient(create_app(repo_root, auth_mode="required"), client=("203.0.113.9", 5000))
        assert _signed_post(c, {"commits": []}, "push").status_code == 200
        assert self._raw(c, {}).status_code == 401
