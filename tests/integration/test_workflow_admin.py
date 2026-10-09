"""Workflows live in the repository's hierarchy.yaml and are editable through the API."""
import copy

import pytest
from click.testing import CliRunner
from ruamel.yaml import YAML

from reqtool.cli import cli


def _formal(client):
    return next(w for w in client.get("/workflows").json()["workflows"] if w["id"] == "formal")


def _yaml(path):
    return YAML(typ="safe").load(path.read_text(encoding="utf-8"))


def test_list_describes_every_workflow(client):
    body = client.get("/workflows").json()
    ids = {w["id"] for w in body["workflows"]}
    assert {"formal", "sprint", "lightweight", "safety_formal"} <= ids
    assert body["types"]["functional"] == "formal"
    assert "content.description" in {f["path"] if isinstance(f, dict) else f for f in body["known_fields"]}
    formal = _formal(client)
    assert formal["errors"] == [] and formal["mermaid"].startswith("flowchart LR")
    assert "functional" in formal["used_by"]


def test_mermaid_endpoints(client):
    r = client.get("/workflows/formal/mermaid")
    assert r.status_code == 200 and "s_draft" in r.json()["mermaid"]
    assert ";" not in r.json()["mermaid"]
    assert client.get("/workflows/nope/mermaid").status_code == 404
    g = client.get("/workflow/mermaid").json()
    assert g["id"] == "global" and g["mermaid"].startswith("flowchart")


def test_save_writes_repo_yaml_and_is_enforced_on_next_transition(client, repo_root):
    definition = copy.deepcopy(_formal(client)["definition"])
    definition["guards"]["in_review"]["requires_fields"] = ["content.rationale"]
    definition["guards"]["in_review"]["message"] = "Say why first."
    r = client.put("/workflows/formal", json=definition)
    assert r.status_code == 200, r.text
    saved = _yaml(repo_root / ".reqtool" / "hierarchy.yaml")
    assert saved["workflows"]["formal"]["guards"]["in_review"]["requires_fields"] == ["content.rationale"]
    uid = client.post("/requirements", json={"title": "Pump"}).json()["uid"]
    blocked = client.put(f"/requirements/{uid}", json={"status": "in_review"})
    assert blocked.status_code == 409, blocked.text
    ok = client.put(f"/requirements/{uid}", json={"status": "in_review", "content": {"rationale": "Safety"}})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "in_review"


def test_invalid_definition_is_422_and_nothing_is_written(client, repo_root):
    definition = copy.deepcopy(_formal(client)["definition"])
    definition["transitions"]["draft"] = ["nowhere"]
    r = client.put("/workflows/formal", json=definition)
    assert r.status_code == 422
    assert not (repo_root / ".reqtool" / "hierarchy.yaml").exists()


def test_preview_does_not_save(client, repo_root):
    definition = copy.deepcopy(_formal(client)["definition"])
    definition["states"].append({"id": "parked", "label": "Parked", "colour": "#123456", "terminal": False})
    definition["transitions"]["parked"] = ["draft"]
    body = client.post("/workflows/preview", json={"id": "formal", "definition": definition}).json()
    assert body["errors"] == [] and "s_parked" in body["mermaid"]
    assert not (repo_root / ".reqtool" / "hierarchy.yaml").exists()
    bad = client.post("/workflows/preview", json={"definition": {"initial": "x", "states": []}}).json()
    assert bad["errors"]


def test_create_clone_and_blank(client):
    r = client.post("/workflows", json={"id": "mine", "copy_from": "formal"})
    assert r.status_code == 201 and r.json()["definition"]["initial"] == "draft"
    blank = client.post("/workflows", json={"id": "blank"})
    assert blank.status_code == 201 and blank.json()["errors"] == []
    assert client.post("/workflows", json={"id": "mine"}).status_code == 409
    assert client.post("/workflows", json={"id": "Bad Id"}).status_code == 422
    assert client.post("/workflows", json={"id": "x1", "copy_from": "ghost"}).status_code == 404


def test_delete_blocked_while_in_use_then_allowed(client):
    r = client.delete("/workflows/formal")
    assert r.status_code == 409 and "functional" in r.text
    client.post("/workflows", json={"id": "spare", "copy_from": "formal"})
    assert client.delete("/workflows/spare").status_code == 200
    assert client.delete("/workflows/spare").status_code == 404


def test_assign_workflow_to_type(client):
    assert client.put("/hierarchy/types/functional/workflow", json={"workflow": "lightweight"}).status_code == 200
    assert client.get("/workflows").json()["types"]["functional"] == "lightweight"
    assert client.put("/hierarchy/types/functional/workflow", json={"workflow": "ghost"}).status_code == 404
    assert client.put("/hierarchy/types/ghost/workflow", json={"workflow": "formal"}).status_code == 404


def test_stranded_status_is_a_warning(client):
    client.post("/requirements", json={"title": "Pump"})
    definition = copy.deepcopy(_formal(client)["definition"])
    definition["states"] = [s for s in definition["states"] if s["id"] != "draft"]
    definition["transitions"].pop("draft")
    for k, v in definition["transitions"].items():
        definition["transitions"][k] = [t for t in v if t != "draft"]
    definition["guards"].pop("draft", None)
    definition["initial"] = "in_review"
    r = client.post("/workflows/preview", json={"id": "formal", "definition": definition}).json()
    assert r["errors"] == []
    assert any("draft" in w for w in r["warnings"])


def test_init_writes_explicit_workflow_and_lint_files(tmp_path):
    out = CliRunner().invoke(cli, ["init", "defaults", "--repo", str(tmp_path / "r"), "--title", "T", "--id", "t"])
    assert out.exit_code == 0, out.output
    hierarchy = _yaml(tmp_path / "r" / ".reqtool" / "hierarchy.yaml")
    assert "formal" in hierarchy["workflows"]
    guard = hierarchy["workflows"]["formal"]["guards"]["draft"]
    assert set(guard) == {"requires_fields", "requires_ac", "requires_children_in", "children_enforce", "message"}
    lint = _yaml(tmp_path / "r" / ".reqtool" / "lint.yaml")
    assert lint["vale"]["binary"] == "vale" and "glossary" in lint and "vague_terms" in lint


def test_migrate_adds_missing_files_and_keeps_existing(repo_root):
    reqtool = repo_root / ".reqtool"
    (reqtool / "lint.yaml").write_text("enabled: false\n", encoding="utf-8")
    out = CliRunner().invoke(cli, ["migrate", "--repo", str(repo_root)])
    assert out.exit_code == 0, out.output
    assert (reqtool / "hierarchy.yaml").exists() and "hierarchy.yaml" in out.output
    assert (reqtool / "lint.yaml").read_text(encoding="utf-8") == "enabled: false\n"
    again = CliRunner().invoke(cli, ["migrate", "--repo", str(repo_root)])
    assert "Wrote" not in again.output
