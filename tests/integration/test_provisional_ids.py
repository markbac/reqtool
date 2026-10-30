"""#349: provisional IDs in shared-repo mode, made sequential on sync, so clones never collide."""
import subprocess

import pytest
import yaml
from click.testing import CliRunner
from fastapi.testclient import TestClient

import reqtool.sync as sync_mod
from reqtool.api import create_app
from reqtool.cli import cli
from reqtool.ids import is_provisional


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("REQTOOL_MODE", raising=False)


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def clones(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    a = tmp_path / "a"
    for d in ("requirements", "principles", "decisions", ".reqtool"):
        (a / d).mkdir(parents=True)
        (a / d / ".keep").write_text("")
    (a / ".reqtool" / "config.yaml").write_text(yaml.safe_dump({"mode": "shared-repo"}))
    _git(a, "init", "-q", "-b", "main")
    _git(a, "config", "user.name", "Ann")
    _git(a, "config", "user.email", "ann@example.com")
    _git(a, "add", "-A")
    _git(a, "commit", "-q", "-m", "base")
    _git(a, "remote", "add", "origin", str(remote))
    _git(a, "push", "-q", "-u", "origin", "main")
    b = tmp_path / "b"
    _git(tmp_path, "clone", "-q", str(remote), str(b))
    _git(b, "config", "user.name", "Bob")
    _git(b, "config", "user.email", "bob@example.com")
    return (a, TestClient(create_app(a))), (b, TestClient(create_app(b)))


def _add(c, title, **fields):
    item = c.post("/requirements", json={"title": title, **fields}).json()
    assert c.post(f"/requirements/{item['uid']}/commit", json={"message": f"add {title}"}).status_code == 200
    return item


def _ids(c):
    return sorted(r["id"] for r in c.get("/requirements").json())


def test_new_items_get_provisional_ids_that_resolve(clones):
    (_, ca), _ = clones
    item = _add(ca, "A")
    assert is_provisional(item["id"]) and item["id"].startswith("FR-~")
    assert ca.get(f"/requirements/{item['id']}").json()["uid"] == item["uid"]


def test_explicit_ids_and_local_mode_are_unchanged(repo_root):
    c = TestClient(create_app(repo_root))
    assert c.post("/requirements", json={"title": "A"}).json()["id"] == "FR-001"
    assert c.post("/requirements", json={"title": "B", "id": "X-9"}).json()["id"] == "X-9"


def test_offline_items_in_two_clones_get_unique_sequential_ids(clones):
    (a, ca), (b, cb) = clones
    first = _add(ca, "Ann's")
    second = _add(cb, "Bob's")
    r = ca.post("/git/sync")
    assert r.status_code == 200, r.text
    assert [f["new"] for f in r.json()["finalised"]] == ["FR-001"]
    r = cb.post("/git/sync")
    assert r.status_code == 200, r.text
    assert [f["new"] for f in r.json()["finalised"]] == ["FR-002"]
    assert r.json()["validation"]["merge_errors"] == []
    ca.post("/git/sync")
    assert _ids(ca) == _ids(cb) == ["FR-001", "FR-002"]
    # the provisional ID still finds the item, and history records the rename
    found = ca.get(f"/requirements/{second['id']}").json()
    assert found["uid"] == second["uid"] and found["id"] == "FR-002"
    assert "ID finalised" in found["history"][-1]["summary"]
    assert _git(a, "log", "-1", "--format=%an %s", "--", f"requirements/{first['uid']}.yaml") == \
        "Ann Finalise provisional IDs"


def test_a_clone_that_pushed_in_between_does_not_cause_a_duplicate(clones, monkeypatch):
    (a, ca), (b, cb) = clones
    _add(ca, "Ann's")
    _add(cb, "Bob's")
    real_push, raced = sync_mod.push, []

    def push(root):
        if root == b and not raced:   # Ann finishes her sync after Bob has finalised but before he pushes
            raced.append(1)
            monkeypatch.setattr(sync_mod, "push", real_push)
            assert ca.post("/git/sync").status_code == 200
            monkeypatch.setattr(sync_mod, "push", push)
        return real_push(root)
    monkeypatch.setattr(sync_mod, "push", push)
    r = cb.post("/git/sync")
    assert r.status_code == 200, r.text
    assert raced and r.json()["validation"]["merge_errors"] == []
    ca.post("/git/sync")
    assert _ids(ca) == _ids(cb) == ["FR-001", "FR-002"]


def test_ids_stay_provisional_on_a_change_set_branch(clones):
    _, (b, cb) = clones
    _git(b, "checkout", "-q", "-b", "changeset/x")
    item = _add(cb, "On branch")
    r = cb.post("/git/sync")
    assert r.status_code == 200, r.text
    assert r.json()["finalised"] == [] and cb.get(f"/requirements/{item['uid']}").json()["id"] == item["id"]


def test_uncommitted_items_wait_for_the_next_sync(clones):
    (a, ca), _ = clones
    item = ca.post("/requirements", json={"title": "draft"}).json()
    assert ca.post("/git/sync").json()["finalised"] == []
    assert ca.get(f"/requirements/{item['uid']}").json()["id"] == item["id"]


def test_acceptance_criteria_ids_follow_the_rename(clones):
    (_, ca), _ = clones
    item = ca.post("/requirements", json={"title": "A"}).json()
    ca.post(f"/requirements/{item['uid']}/ac", json={"text": "works"})
    ca.post(f"/requirements/{item['uid']}/commit", json={"message": "add"})
    ca.post("/git/sync")
    acs = ca.get(f"/requirements/{item['uid']}").json()["acceptance_criteria"]
    assert acs[0]["id"].startswith("FR-001__AC-")


def test_finalise_ids_cli_commits(clones):
    (a, ca), _ = clones
    _add(ca, "A")
    r = CliRunner().invoke(cli, ["finalise-ids", "--repo", str(a)])
    assert r.exit_code == 0, r.output
    assert "as FR-001" in r.output
    assert _git(a, "status", "--porcelain", "requirements") == ""
    assert _git(a, "log", "-1", "--format=%an") == "Ann"


def test_fix_ids_renumbers_the_newer_duplicate(repo_root):
    c = TestClient(create_app(repo_root))
    old = c.post("/requirements", json={"title": "old", "id": "FR-001"}).json()
    new = c.post("/requirements", json={"title": "new", "id": "FR-002"}).json()
    path = repo_root / "requirements" / f"{new['uid']}.yaml"
    path.write_text(path.read_text().replace("id: FR-002", "id: FR-001"))
    r = CliRunner().invoke(cli, ["fix-ids", "--repo", str(repo_root)])
    assert r.exit_code == 0, r.output
    assert f"Renumbered FR-001 ({new['uid']}) as FR-002" in r.output
    c = TestClient(create_app(repo_root))
    assert c.get(f"/requirements/{old['uid']}").json()["id"] == "FR-001"
