"""INT-04: baseline diff and compare return real results."""
import subprocess

from fastapi.testclient import TestClient

from reqtool.api import create_app
from tests.conftest import make_req


def _git(root, *a):
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)


def _commit_all(root, msg):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", msg)


def _setup(repo_root):
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "t@t")
    _git(repo_root, "config", "user.name", "t")
    return TestClient(create_app(repo_root))


def test_diff_and_compare(repo_root):
    c = _setup(repo_root)
    keep = make_req(c, title="keep")["uid"]
    gone = make_req(c, title="gone")["uid"]
    _commit_all(repo_root, "base")
    assert c.post("/baselines", json={"name": "b1"}).status_code == 201

    make_req(c, title="new1")
    assert c.put(f"/requirements/{keep}", json={"title": "keep2"}).status_code == 200
    assert c.delete(f"/requirements/{gone}").status_code in (200, 204)
    _commit_all(repo_root, "second")
    assert c.post("/baselines", json={"name": "b2"}).status_code == 201

    make_req(c, title="new2")
    _commit_all(repo_root, "third")

    r = c.get("/baselines/b1/diff")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["baseline"] == "baseline/b1"
    assert len(d["added"]) == 2
    assert len(d["changed"]) >= 1

    # compare b1..b2 must NOT include new2 (it was added after b2)
    r = c.get("/baselines/compare", params={"baseline_a": "b1", "baseline_b": "b2"})
    assert r.status_code == 200, r.text
    cmp = r.json()
    assert cmp["summary"]["added"] == 1
    assert cmp["summary"]["modified"] >= 1


def test_unknown_baseline_is_404(repo_root):
    c = _setup(repo_root)
    assert c.get("/baselines/nope/diff").status_code == 404
    assert c.get("/baselines/compare", params={"baseline_a": "x", "baseline_b": "y"}).status_code == 404
