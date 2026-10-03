"""DAT-15: a baseline never silently omits uncommitted artefact edits."""
import subprocess

import pytest
from fastapi.testclient import TestClient

from reqtool.api import create_app
from tests.conftest import make_req
from tests.test_baseline_diff import _commit_all, _setup


def test_dirty_tree_is_409_with_ids_then_clean_tree_succeeds(repo_root):
    c = _setup(repo_root)
    a = make_req(c, title="A", id="FR-1")
    _commit_all(repo_root, "base")
    c.put(f"/requirements/{a['uid']}", json={"title": "edited"})
    make_req(c, title="B", id="FR-2")  # untracked file
    r = c.post("/baselines", json={"name": "b1"})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["error"] == "dirty_working_tree" and d["uncommitted"] == ["FR-1", "FR-2"]
    assert c.get("/baselines").json() == []
    _commit_all(repo_root, "work")
    assert c.post("/baselines", json={"name": "b1"}).status_code == 201


def test_allow_dirty_records_the_list_in_the_tag_message(repo_root):
    c = _setup(repo_root)
    a = make_req(c, title="A", id="FR-1")
    _commit_all(repo_root, "base")
    c.put(f"/requirements/{a['uid']}", json={"title": "edited"})
    r = c.post("/baselines", json={"name": "b1", "allow_dirty": True})
    assert r.status_code == 201 and r.json()["uncommitted"] == ["FR-1"]
    msg = subprocess.run(["git", "tag", "-n99", "baseline/b1"], cwd=repo_root, capture_output=True, text=True).stdout
    assert "FR-1" in msg and "uncommitted" in msg


def test_unrelated_dirty_files_do_not_block(repo_root):
    c = _setup(repo_root)
    make_req(c, title="A")
    _commit_all(repo_root, "base")
    (repo_root / "notes.txt").write_text("scratch")
    assert c.post("/baselines", json={"name": "b1"}).status_code == 201
