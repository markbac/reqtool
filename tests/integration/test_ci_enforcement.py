"""#351: in shared-repo mode CI enforces the workflow: `req check-changes` and the `req ci init` template."""
import subprocess

import pytest
import yaml
from click.testing import CliRunner
from fastapi.testclient import TestClient

from reqtool import __version__
from reqtool.api import create_app
from reqtool.cli import cli


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("REQTOOL_MODE", raising=False)


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(repo_root):
    _git(repo_root, "init", "-q", "-b", "main")
    _git(repo_root, "config", "user.name", "Ann")
    _git(repo_root, "config", "user.email", "ann@example.com")
    c = TestClient(create_app(repo_root))
    item = c.post("/requirements", json={"title": "A"}).json()
    issue = c.post("/requirements", json={"title": "Broken", "req_type": "issue"}).json()
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "-m", "base")
    _git(repo_root, "checkout", "-q", "-b", "feature")
    return repo_root, c, item, issue


def _check(root):
    return CliRunner().invoke(cli, ["check-changes", "--base", "main", "--repo", str(root)])


def _commit(root):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "change")


def _hand_edit(root, uid, **fields):
    path = root / "requirements" / f"{uid}.yaml"
    data = yaml.safe_load(path.read_text())
    data.update(fields)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_moves_made_through_reqtool_pass(repo):
    root, c, item, _ = repo
    for to in ("in_review", "reviewed"):
        assert c.post(f"/requirements/{item['uid']}/transition", json={"to_state": to}).status_code == 200
    _commit(root)
    r = _check(root)
    assert r.exit_code == 0, r.output


def test_a_skipped_state_fails(repo):
    root, _, item, _ = repo
    _hand_edit(root, item["uid"], status="approved")
    _commit(root)
    r = _check(root)
    assert r.exit_code == 1 and "illegal_transition" in r.output and item["id"] in r.output


def test_an_unmet_guard_fails(repo):
    root, _, _, issue = repo
    _hand_edit(root, issue["uid"], status="in_triage")      # needs an assignee
    _commit(root)
    r = _check(root)
    assert r.exit_code == 1 and "workflow_guard" in r.output
    _hand_edit(root, issue["uid"], assignee="ann")
    _commit(root)
    assert _check(root).exit_code == 0


def test_history_that_does_not_lead_to_the_status_fails(repo):
    root, c, item, _ = repo
    c.post(f"/requirements/{item['uid']}/transition", json={"to_state": "in_review"})
    _hand_edit(root, item["uid"], status="reviewed")
    _commit(root)
    r = _check(root)
    assert r.exit_code == 1 and "status_history_gap" in r.output


def test_a_new_item_must_start_in_the_initial_state(repo):
    root, c, _, _ = repo
    new = c.post("/requirements", json={"title": "B"}).json()
    _hand_edit(root, new["uid"], status="approved")
    _commit(root)
    r = _check(root)
    assert r.exit_code == 1 and "created_past_initial" in r.output


def test_ci_init_writes_the_workflow_and_codeowners(repo_root):
    r = CliRunner().invoke(cli, ["ci", "init", "--repo", str(repo_root), "--codeowners", "@org/req-admins"])
    assert r.exit_code == 0, r.output
    wf = yaml.safe_load((repo_root / ".github" / "workflows" / "reqtool.yml").read_text())
    steps = [s.get("run", "") for s in wf["jobs"]["check"]["steps"]]
    assert "req validate" in steps and "req verify" in steps
    assert any("req check-changes" in s for s in steps)
    assert any(f"@v{__version__}" in s for s in steps)
    assert wf[True]["push"]["branches"] == ["main"]      # PyYAML reads the key `on` as True
    assert "req finalise-ids" in wf["jobs"]["finalise-ids"]["steps"][-1]["run"]
    assert "/.reqtool/ @org/req-admins" in (repo_root / ".github" / "CODEOWNERS").read_text()
    r = CliRunner().invoke(cli, ["ci", "init", "--repo", str(repo_root)])
    assert "exists; use --force" in r.output
