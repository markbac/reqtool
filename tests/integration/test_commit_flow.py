"""DAT-03: committing one artefact commits only that file and leaves the tree clean."""
import subprocess

import yaml
from fastapi.testclient import TestClient

from reqtool.api import create_app
from tests.conftest import make_req


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _setup(repo_root):
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "t@t")
    _git(repo_root, "config", "user.name", "t")
    c = TestClient(create_app(repo_root))
    a = make_req(c, title="A")["uid"]
    b = make_req(c, title="B")["uid"]
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "-m", "base")
    return c, a, b


def test_commits_only_the_target_file_and_leaves_other_staged(repo_root):
    c, a, b = _setup(repo_root)
    c.put(f"/requirements/{a}", json={"title": "A2"})
    c.put(f"/requirements/{b}", json={"title": "B2"})
    _git(repo_root, "add", f"requirements/{b}.yaml")  # unrelated staged change
    r = c.post(f"/requirements/{a}/commit", json={"message": "commit A only"})
    assert r.status_code == 200, r.text
    files = _git(repo_root, "show", "--name-only", "--pretty=format:", "HEAD").split()
    assert files == [f"requirements/{a}.yaml"]
    staged = _git(repo_root, "diff", "--cached", "--name-only").split()
    assert staged == [f"requirements/{b}.yaml"]


def test_working_tree_clean_after_commit_and_no_sha_in_file(repo_root):
    c, a, _ = _setup(repo_root)
    c.put(f"/requirements/{a}", json={"title": "A2"})
    r = c.post(f"/requirements/{a}/commit", json={"message": "commit A"})
    assert r.status_code == 200
    assert _git(repo_root, "status", "--porcelain", "--", f"requirements/{a}.yaml") == ""
    data = yaml.safe_load((repo_root / "requirements" / f"{a}.yaml").read_text())
    assert all(not h.get("commit_sha") for h in data["history"])


def test_history_endpoint_still_shows_commit_sha(repo_root):
    c, a, _ = _setup(repo_root)
    c.put(f"/requirements/{a}", json={"title": "A2"})
    sha = c.post(f"/requirements/{a}/commit", json={"message": "commit A"}).json()["commit_sha"]
    hist = c.get(f"/requirements/{a}/history").json()["in_file"]
    assert hist[-1]["commit_sha"] == sha[:7]
