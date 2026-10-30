"""#348: fetch, pull, push and sync the requirements repository with a remote (a local bare repository here)."""
import subprocess

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.cli import cli


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("REQTOOL_MODE", raising=False)


def _git(root, *a, check=True):
    return subprocess.run(["git", *a], cwd=root, check=check, capture_output=True, text=True).stdout.strip()


def _identity(root, name):
    _git(root, "config", "user.name", name)
    _git(root, "config", "user.email", f"{name.lower()}@example.com")


@pytest.fixture
def clones(tmp_path):
    """A remote and two clones of it, each with its own reqtool app."""
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    a = tmp_path / "a"
    a.mkdir()
    for d in ("requirements", "principles", "decisions", ".reqtool"):
        (a / d).mkdir()
        (a / d / ".keep").write_text("")
    _git(a, "init", "-q", "-b", "main")
    _identity(a, "Ann")
    _git(a, "add", "-A")
    _git(a, "commit", "-q", "-m", "base")
    _git(a, "remote", "add", "origin", str(remote))
    _git(a, "push", "-q", "-u", "origin", "main")
    b = tmp_path / "b"
    _git(tmp_path, "clone", "-q", str(remote), str(b))
    _identity(b, "Bob")
    return remote, (a, TestClient(create_app(a))), (b, TestClient(create_app(b)))


def _add(c, root, title, **fields):
    uid = c.post("/requirements", json={"title": title, **fields}).json()["uid"]
    assert c.post(f"/requirements/{uid}/commit", json={"message": f"add {title}"}).status_code == 200
    return uid


def test_changes_flow_between_clones(clones):
    _, (a, ca), (b, cb) = clones
    uid = _add(cb, b, "From Bob")
    st = cb.get("/git/status").json()["sync"]
    assert st["branch"] == "main" and st["upstream"] == "origin/main" and st["ahead"] == 1

    r = cb.post("/git/sync")
    assert r.status_code == 200, r.text
    assert r.json()["pushed"] and r.json()["ahead"] == 0

    assert ca.post("/git/fetch").json()["behind"] == 1
    r = ca.post("/git/sync")
    assert r.status_code == 200, r.text
    assert any(p.startswith("requirements/") for p in r.json()["changed"])
    assert ca.get(f"/requirements/{uid}").json()["title"] == "From Bob"
    assert r.json()["validation"]["merge_errors"] == []


def test_local_commits_are_rebased_over_the_remote(clones):
    _, (a, ca), (b, cb) = clones
    _add(cb, b, "B1")
    cb.post("/git/sync")
    _add(ca, a, "A1")
    r = ca.post("/git/sync")
    assert r.status_code == 200, r.text
    assert r.json()["pushed"] and r.json()["behind"] == 0
    assert _git(a, "log", "--format=%s").splitlines()[:2] == ["add A1", "add B1"]


def test_conflict_leaves_merge_state_and_blocks_writes(clones):
    _, (a, ca), (b, cb) = clones
    uid = _add(ca, a, "Shared", id="REQ-100")
    ca.post("/git/sync")
    cb.post("/git/sync")
    cb.put(f"/requirements/{uid}", json={"title": "Bob's"})
    cb.post(f"/requirements/{uid}/commit", json={"message": "bob"})
    cb.post("/git/sync")
    ca.put(f"/requirements/{uid}", json={"title": "Ann's"})
    ca.post(f"/requirements/{uid}/commit", json={"message": "ann"})
    r = ca.post("/git/sync")
    assert r.status_code == 409 and r.json()["detail"]["error"] == "conflict"
    assert ca.post("/requirements", json={"title": "x"}).status_code == 409
    assert ca.post("/git/sync").json()["detail"]["error"] == "conflict"


def test_validation_findings_from_the_merge_are_reported(clones):
    _, (a, ca), (b, cb) = clones
    _add(ca, a, "Ann's", id="REQ-007")
    _add(cb, b, "Bob's", id="REQ-007")
    cb.post("/git/sync")
    r = ca.post("/git/sync")
    assert r.status_code == 200, r.text
    assert "duplicate_id" in {e["code"] for e in r.json()["validation"]["merge_errors"]}


def test_first_push_of_a_new_branch_sets_upstream(clones):
    remote, _, (b, cb) = clones
    _git(b, "checkout", "-q", "-b", "changeset/x")
    _add(cb, b, "On branch")
    r = cb.post("/git/push")
    assert r.status_code == 200, r.text
    assert r.json()["upstream"] == "origin/changeset/x"
    assert "changeset/x" in _git(remote, "branch")


def test_protected_branch_gives_a_helpful_message(clones):
    remote, _, (b, cb) = clones
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'protected branch hook declined' >&2\nexit 1\n")
    hook.chmod(0o755)
    _add(cb, b, "Blocked")
    r = cb.post("/git/push")
    assert r.status_code == 409 and r.json()["detail"]["error"] == "protected_branch"
    assert "change set" in r.json()["detail"]["message"]


def test_rejected_push_says_to_sync(clones):
    _, (a, ca), (b, cb) = clones
    _add(ca, a, "A")
    ca.post("/git/push")
    _add(cb, b, "B")
    r = cb.post("/git/push")
    assert r.status_code == 409 and r.json()["detail"]["error"] == "behind"


def test_no_remote(repo_root):
    _git(repo_root, "init", "-q")
    r = TestClient(create_app(repo_root)).post("/git/sync")
    assert r.status_code == 409 and r.json()["detail"]["error"] == "no_remote"


def test_cli_sync(clones):
    _, (a, ca), (b, cb) = clones
    _add(cb, b, "CLI")
    r = CliRunner().invoke(cli, ["sync", "--repo", str(b)])
    assert r.exit_code == 0, r.output
    assert "Pushed origin/main" in r.output
    r = CliRunner().invoke(cli, ["sync", "--repo", str(a), "--no-push"])
    assert r.exit_code == 0 and "Pulled 1 changed file(s)" in r.output
