"""UI-10: the UI's API calls must match the server contract."""
import subprocess

from fastapi.testclient import TestClient

from reqtool.api import create_app
from tests.conftest import make_req


def _git(root, *a):
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)


def test_reqif_export_is_get(client):
    assert client.get("/export/reqif").status_code == 200
    assert client.post("/export/reqif", json={}).status_code == 405


def test_transition_requires_to_state(client):
    uid = make_req(client)["uid"]
    r = client.post(f"/requirements/{uid}/transition", json={"status": "approved"})
    assert r.status_code == 422
    r = client.post(f"/requirements/{uid}/transition", json={"to_state": "bogus"})
    assert r.status_code != 404


def test_global_commit_with_nothing_staged_is_409_not_500(repo_root):
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "t@t")
    _git(repo_root, "config", "user.name", "t")
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "--allow-empty", "-m", "base")
    c = TestClient(create_app(repo_root))
    r = c.post("/git/commit", json={"message": "x", "uids": []})
    assert r.status_code == 409, r.text
    assert "Nothing staged" in r.text


def test_global_commit_commits_already_staged_files(repo_root):
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "t@t")
    _git(repo_root, "config", "user.name", "t")
    (repo_root / "note.txt").write_text("hi")
    _git(repo_root, "add", "note.txt")
    c = TestClient(create_app(repo_root))
    r = c.post("/git/commit", json={"message": "x", "uids": []})
    assert r.status_code == 200, r.text
    assert r.json()["commit_sha"]
