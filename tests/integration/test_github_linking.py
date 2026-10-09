"""INT-01: commit linking resolves human IDs, ignores non-requirements and does not version the requirement."""
import hashlib
import hmac
import json

import pytest

from tests.conftest import make_req

SECRET = "s3cret"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("REQTOOL_GITHUB_WEBHOOK_SECRET", SECRET)


def _push(client, *messages, sha="abc1234567890"):
    commits = [{"id": f"{sha}{i}", "message": m, "author": {"username": "dev"}} for i, m in enumerate(messages)]
    body = json.dumps({"ref": "refs/heads/main", "repository": {"full_name": "org/dev"}, "commits": commits}).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    r = client.post("/webhooks/github", content=body, headers={
        "X-GitHub-Event": "push", "X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    return r.json()


def _req(client, rid="FR-001"):
    return make_req(client, title="t", id=rid)


def test_fixes_human_id_links_exactly_one_without_a_new_version(client):
    req = _req(client)
    before = client.get(f"/requirements/{req['uid']}").json()
    out = _push(client, "Fixes FR-001 and bumps UTF-8 handling")
    assert out["processed_links"] == 1 and out["details"][0]["uid"] == req["uid"]
    after = client.get(f"/requirements/{req['uid']}").json()
    assert after["version"] == before["version"]
    assert len(after.get("history", [])) == len(before.get("history", []))
    assert after["content_hash"] == before["content_hash"]
    links = client.get(f"/requirements/{req['uid']}/commits").json()
    assert len(links) == 1 and links[0]["sha"].startswith("abc12345") and links[0]["repo"] == "org/dev"


def test_non_requirement_lookalikes_link_nothing(client):
    _req(client)
    out = _push(client, "Use UTF-8, see ISO-26262 and CVE-2024-1234")
    assert out["processed_links"] == 0


def test_lowercase_and_uid_references_resolve(client):
    req = _req(client, "FR-007")
    assert _push(client, "refs fr-007")["processed_links"] == 1
    assert _push(client, f"see {req['uid'].upper()}", sha="def9876543210")["processed_links"] == 1


def test_same_commit_is_not_linked_twice(client):
    req = _req(client)
    _push(client, "Fixes FR-001")
    assert _push(client, "Fixes FR-001")["processed_links"] == 0
    assert len(client.get(f"/requirements/{req['uid']}/commits").json()) == 1


def test_deleted_requirements_are_not_linked(client):
    req = _req(client)
    client.delete(f"/requirements/{req['uid']}")
    assert _push(client, "Fixes FR-001")["processed_links"] == 0


def test_commits_endpoint_404_for_unknown(client):
    assert client.get("/requirements/nope/commits").status_code == 404
