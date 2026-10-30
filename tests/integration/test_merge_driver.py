"""#350: reqtool's git merge driver merges artefact YAML field by field."""
import re
import subprocess

import pytest
import yaml
from click.testing import CliRunner
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.cli import cli
from reqtool.features.doctor import run_doctor
from reqtool.fileio import compute_requirement_hash
from reqtool.merge import merge_documents
from reqtool.store import Store


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("REQTOOL_MODE", raising=False)


def _doc(**over):
    base = {"id": "FR-001", "title": "T", "content": {"description": "d", "rationale": "r"}, "tags": ["a"],
            "acceptance_criteria": [{"uid": "ac1", "text": "one"}], "version": "1.0.0", "last_modified": "2026-01-01",
            "history": [{"version": "1.0.0", "date": "2026-01-01", "modified_by": "x", "summary": "Initial."}]}
    base.update(over)
    base["content_hash"] = compute_requirement_hash(base)
    return base


def _edit(doc, version, date, who, **fields):
    out = {**doc, **fields, "version": version, "last_modified": date,
           "history": doc["history"] + [{"version": version, "date": date, "modified_by": who, "summary": "edit"}]}
    out["content_hash"] = compute_requirement_hash(out)
    return out


def test_edits_to_different_fields_merge_cleanly():
    base = _doc()
    ours = _edit(base, "1.0.1", "2026-02-01", "ann", title="New title", tags=["a", "b"])
    theirs = _edit(base, "1.1.0", "2026-02-02", "bob", content={"description": "d", "rationale": "better"},
                   tags=["a", "c"], acceptance_criteria=[{"uid": "ac1", "text": "one"}, {"uid": "ac2", "text": "two"}])
    merged, sides = merge_documents(base, ours, theirs, compute_requirement_hash, "carol", now="2026-03-01")
    assert sides is None
    assert merged["title"] == "New title" and merged["content"]["rationale"] == "better"
    assert merged["tags"] == ["a", "b", "c"] and [a["uid"] for a in merged["acceptance_criteria"]] == ["ac1", "ac2"]
    assert merged["version"] == "1.1.1" and merged["last_modified"] == "2026-03-01"
    assert [h["modified_by"] for h in merged["history"]] == ["x", "ann", "bob", "carol"]
    assert merged["content_hash"] == compute_requirement_hash(merged)


def test_a_one_sided_change_is_taken_without_a_merge_entry():
    base = _doc()
    theirs = _edit(base, "1.0.1", "2026-02-01", "bob", title="B")
    merged, sides = merge_documents(base, base, theirs, compute_requirement_hash, "carol")
    assert sides is None and merged["version"] == "1.0.1" and len(merged["history"]) == 2


def test_removing_a_tag_on_one_side_sticks():
    base = _doc(tags=["a", "b"])
    ours = _edit(base, "1.0.1", "2026-02-01", "ann", tags=["a"])
    theirs = _edit(base, "1.0.1", "2026-02-02", "bob", tags=["a", "b", "c"])
    merged, _ = merge_documents(base, ours, theirs, compute_requirement_hash, "carol")
    assert merged["tags"] == ["a", "c"]


def test_the_same_field_changed_differently_conflicts():
    base = _doc()
    ours = _edit(base, "1.0.1", "2026-02-01", "ann", title="Ann's", priority="high")
    theirs = _edit(base, "1.0.1", "2026-02-02", "bob", title="Bob's")
    _, sides = merge_documents(base, ours, theirs, compute_requirement_hash, "carol")
    assert sides is not None
    assert [s["title"] for s in sides] == ["Ann's", "T", "Bob's"]
    assert all(s["priority"] == "high" for s in sides)        # the clean part is merged in every side


# ---------------------------------------------------------------------------- through git

def _git(root, *a, check=True):
    return subprocess.run(["git", *a], cwd=root, check=check, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def clones(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    a = tmp_path / "a"
    for d in ("requirements", "principles", "decisions", ".reqtool"):
        (a / d).mkdir(parents=True)
        (a / d / ".keep").write_text("")
    _git(a, "init", "-q", "-b", "main")
    _git(a, "config", "user.name", "Ann")
    _git(a, "config", "user.email", "ann@example.com")
    assert CliRunner().invoke(cli, ["setup", "--repo", str(a)]).exit_code == 0
    c = TestClient(create_app(a))
    uid = c.post("/requirements", json={"title": "Shared", "content": {"description": "d", "rationale": "r"}}).json()["uid"]
    _git(a, "add", "-A")
    _git(a, "commit", "-q", "-m", "base")
    _git(a, "remote", "add", "origin", str(remote))
    _git(a, "push", "-q", "-u", "origin", "main")
    b = tmp_path / "b"
    _git(tmp_path, "clone", "-q", str(remote), str(b))
    _git(b, "config", "user.name", "Bob")
    _git(b, "config", "user.email", "bob@example.com")
    return uid, (a, c), (b, TestClient(create_app(b)))


def test_concurrent_edits_to_one_item_merge_through_sync(clones):
    uid, (a, ca), (b, cb) = clones
    cb.put(f"/requirements/{uid}", json={"priority": "high"})
    cb.post(f"/requirements/{uid}/commit", json={"message": "bob"})
    assert cb.post("/git/sync").status_code == 200
    ca.put(f"/requirements/{uid}", json={"title": "Better title"})
    ca.post(f"/requirements/{uid}/commit", json={"message": "ann"})
    r = ca.post("/git/sync")
    assert r.status_code == 200, r.text
    item = ca.get(f"/requirements/{uid}").json()
    assert item["title"] == "Better title" and item["priority"] == "high"
    assert "Merged concurrent changes." in [h["summary"] for h in item["history"]]
    assert CliRunner().invoke(cli, ["verify", "--repo", str(a)]).exit_code == 0


def test_sync_registers_the_driver_in_a_fresh_clone(clones):
    uid, (a, ca), (b, cb) = clones
    assert _git(b, "config", "merge.reqtool.driver", check=False) == ""
    ca.put(f"/requirements/{uid}", json={"priority": "low"})
    ca.post(f"/requirements/{uid}/commit", json={"message": "ann"})
    ca.post("/git/sync")
    cb.put(f"/requirements/{uid}", json={"title": "Bob's title"})
    cb.post(f"/requirements/{uid}/commit", json={"message": "bob"})
    r = cb.post("/git/sync")
    assert r.status_code == 200, r.text
    assert r.json()["merge_driver_installed"] is True
    item = cb.get(f"/requirements/{uid}").json()
    assert item["title"] == "Bob's title" and item["priority"] == "low"


def test_a_real_conflict_marks_only_that_field_and_can_be_resolved(clones):
    uid, (a, ca), (b, cb) = clones
    cb.put(f"/requirements/{uid}", json={"title": "Bob's", "priority": "high"})
    cb.post(f"/requirements/{uid}/commit", json={"message": "bob"})
    cb.post("/git/sync")
    ca.put(f"/requirements/{uid}", json={"title": "Ann's"})
    ca.post(f"/requirements/{uid}/commit", json={"message": "ann"})
    r = ca.post("/git/sync")
    assert r.status_code == 409 and r.json()["detail"]["error"] == "conflict"
    path = a / "requirements" / f"{uid}.yaml"
    text = path.read_text()
    block = text[text.index("<<<<<<<"):text.index(">>>>>>>")]
    assert "title" in block and "priority" not in block and "content_hash" not in block
    # resolve by keeping the upstream side (Bob's title): during a rebase that is "ours"
    out = re.sub(r"<<<<<<< ours\n(.*?)=======\n.*?>>>>>>> theirs\n", r"\1", text, flags=re.S)
    path.write_text(out)
    r = CliRunner().invoke(cli, ["resolved", str(path), "--repo", str(a)])
    assert r.exit_code == 0, r.output
    _git(a, "-c", "core.editor=true", "rebase", "--continue")
    assert CliRunner().invoke(cli, ["verify", "--repo", str(a)]).exit_code == 0
    data = yaml.safe_load(path.read_text())
    assert data["title"] == "Bob's" and data["priority"] == "high"
    assert data["history"][-1]["summary"] == "Resolved merge conflict."


def test_resolved_refuses_files_with_markers(clones, tmp_path):
    uid, (a, _), _ = clones
    path = a / "requirements" / f"{uid}.yaml"
    path.write_text(path.read_text() + "<<<<<<< ours\n")
    r = CliRunner().invoke(cli, ["resolved", str(path), "--repo", str(a)])
    assert r.exit_code != 0 and "conflict markers" in r.output


def test_doctor_reports_missing_driver(repo_root):
    (repo_root / ".reqtool" / "config.yaml").write_text(yaml.safe_dump({"mode": "shared-repo"}))
    _git(repo_root, "init", "-q")
    s = Store(repo_root)
    s.load()
    codes = {c["code"] for c in run_doctor(s)["checks"]}
    assert {"merge_attributes_missing", "merge_driver_missing"} <= codes
    CliRunner().invoke(cli, ["setup", "--repo", str(repo_root)])
    codes = {c["code"] for c in run_doctor(s)["checks"]}
    assert not codes & {"merge_attributes_missing", "merge_driver_missing"}
