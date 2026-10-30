"""#347: the git author is the person who made the change, in every mode."""
import subprocess

import pytest
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.auth import UserStore
from reqtool.identity import Identity, attribution, uncommitted_editors
from reqtool.models import RepoConfig
from tests.conftest import make_req

PW = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _no_global_identity(monkeypatch):
    """Only the repository's own git config counts, whatever the machine running the tests has."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("REQTOOL_MODE", raising=False)


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _init(root, name="Ann Smith", email="ann@example.com"):
    _git(root, "init", "-q")
    if name:
        _git(root, "config", "user.name", name)
        _git(root, "config", "user.email", email)


def _last(root, fmt):
    return _git(root, "log", "-1", f"--format={fmt}")


def test_local_commit_uses_the_users_git_identity(repo_root):
    _init(repo_root)
    c = TestClient(create_app(repo_root))
    uid = make_req(c, title="A")["uid"]
    r = c.post(f"/requirements/{uid}/commit", json={"message": "add A"})
    assert r.status_code == 200, r.text
    assert _last(repo_root, "%an <%ae>|%cn <%ce>") == "Ann Smith <ann@example.com>|Ann Smith <ann@example.com>"
    history = c.get(f"/requirements/{uid}").json()["history"]
    assert {h["modified_by"] for h in history} == {"Ann Smith"}


def test_explicit_author_names_are_kept_in_local_mode(repo_root):
    _init(repo_root)
    c = TestClient(create_app(repo_root))
    uid = make_req(c, title="A")["uid"]
    c.post(f"/artefacts/{uid}/comments", json={"text": "hi", "author": "Bob"})
    c.post(f"/artefacts/{uid}/comments", json={"text": "hi"})
    assert [x["author"] for x in c.get(f"/artefacts/{uid}/comments").json()] == ["Bob", "Ann Smith"]


def test_commit_without_identity_is_refused_and_changes_nothing(repo_root):
    _init(repo_root, name=None)
    c = TestClient(create_app(repo_root))
    uid = make_req(c, title="A")["uid"]
    before = c.get(f"/requirements/{uid}").json()
    r = c.post(f"/requirements/{uid}/commit", json={"message": "add A"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "no_git_identity"
    assert "git config" in r.json()["detail"]["message"]
    assert c.get(f"/requirements/{uid}").json()["version"] == before["version"]
    r = c.post("/baselines", json={"name": "b1", "allow_dirty": True})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "no_git_identity"


def test_baseline_tagger_is_the_user(repo_root):
    _init(repo_root)
    c = TestClient(create_app(repo_root))
    make_req(c, title="A")
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "-m", "base")
    assert c.post("/baselines", json={"name": "b1"}).status_code == 201
    assert _git(repo_root, "for-each-ref", "--format=%(taggername) %(taggeremail)", "refs/tags/baseline/b1") == \
        "Ann Smith <ann@example.com>"


@pytest.fixture
def server(repo_root):
    _init(repo_root, name=None)
    users = UserStore(repo_root)
    users.create_user("alice", PW, full_name="Alice Jones", email="alice@corp.example", role="editor")
    users.create_user("bob", PW, full_name="Bob Lee", email="bob@corp.example", role="editor")
    users.create_user("carol", PW, role="editor")
    c = TestClient(create_app(repo_root, auth_mode="required"))

    def login(name):
        token = c.post("/auth/login", json={"username": name, "password": PW}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return c, login


def test_server_author_is_the_editor_and_committer_is_the_server(server, repo_root):
    c, login = server
    alice, bob = login("alice"), login("bob")
    uid = c.post("/requirements", json={"title": "A"}, headers=alice).json()["uid"]
    r = c.post(f"/requirements/{uid}/commit", json={"message": "add A"}, headers=bob)
    assert r.status_code == 200, r.text
    assert _last(repo_root, "%an <%ae>") == "Alice Jones <alice@corp.example>"
    assert _last(repo_root, "%cn <%ce>") == "Requirements Tool <reqtool@example.com>"
    assert "Committed-by: Bob Lee <bob@corp.example>" in _last(repo_root, "%B")


def test_server_several_editors_become_co_authors(server, repo_root):
    c, login = server
    alice, bob, carol = login("alice"), login("bob"), login("carol")
    uid = c.post("/requirements", json={"title": "A"}, headers=alice).json()["uid"]
    c.post(f"/requirements/{uid}/commit", json={"message": "add A"}, headers=alice)
    c.put(f"/requirements/{uid}", json={"title": "A2"}, headers=bob)
    c.put(f"/requirements/{uid}", json={"title": "A3"}, headers=carol)
    r = c.post(f"/requirements/{uid}/commit", json={"message": "edit A"}, headers=carol)
    assert r.status_code == 200, r.text
    # carol has no email: the committer's domain is used
    assert _last(repo_root, "%an <%ae>") == "Carol <carol@example.com>"
    body = _last(repo_root, "%B")
    assert "Co-authored-by: Bob Lee <bob@corp.example>" in body
    assert "Alice" not in body and "Committed-by" not in body


def test_server_batch_commit_makes_one_commit_per_author(server, repo_root):
    c, login = server
    alice, bob = login("alice"), login("bob")
    a = c.post("/requirements", json={"title": "A"}, headers=alice).json()["uid"]
    b = c.post("/requirements", json={"title": "B"}, headers=bob).json()["uid"]
    r = c.post("/git/commit", json={"message": "batch", "uids": [a, b]}, headers=bob)
    assert r.status_code == 200, r.text
    assert len(r.json()["commits"]) == 2
    authors = _git(repo_root, "log", "--format=%an").splitlines()
    assert sorted(authors) == ["Alice Jones", "Bob Lee"]
    assert _git(repo_root, "status", "--porcelain", "requirements") == ""


def test_uncommitted_editors_survive_trimmed_history(repo_root):
    _init(repo_root)
    path = repo_root / "requirements" / "x.yaml"
    old = [{"version": f"1.0.{i}", "date": f"d{i}", "summary": "s", "modified_by": "old"} for i in range(3)]
    path.write_text("history:\n" + "".join(
        f"- {{version: '{h['version']}', date: {h['date']}, summary: s, modified_by: old}}\n" for h in old))
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "-m", "base")
    new = old[1:] + [{"version": "1.0.3", "date": "d3", "summary": "s", "modified_by": "ann"},
                     {"version": "1.0.4", "date": "d4", "summary": "s", "modified_by": "bob"},
                     {"version": "1.0.5", "date": "d5", "summary": "s", "modified_by": "ann"}]
    assert uncommitted_editors(repo_root, path, new) == ["bob", "ann"]


def test_attribution_without_login_needs_identity(repo_root):
    _init(repo_root)
    who = attribution(repo_root, RepoConfig(), ["someone"], None)
    assert who.author == who.committer == Identity("Ann Smith", "ann@example.com") and who.trailers == []


def test_doctor_warns_about_missing_or_tool_identity(repo_root):
    from reqtool.features.doctor import run_doctor
    from reqtool.store import Store
    _init(repo_root, name=None)
    s = Store(repo_root)
    s.load()
    assert "no_git_identity" in {c["code"] for c in run_doctor(s)["checks"]}
    _git(repo_root, "config", "user.name", "Requirements Tool")
    _git(repo_root, "config", "user.email", "reqtool@example.com")
    assert "tool_git_identity" in {c["code"] for c in run_doctor(s)["checks"]}
