"""The writing check over HTTP and the command line, and how it relates to validation."""
import json

from click.testing import CliRunner
from ruamel.yaml import YAML

from reqtool.cli import cli


def _make(client, description="In order to work the api is fast.", **extra):
    r = client.post("/requirements", json={"title": "Pump", "content": {"description": description}, **extra})
    assert r.status_code == 201, r.text
    return r.json()["uid"]


def test_config_defaults_show_every_setting(client):
    body = client.get("/lint/config").json()
    assert body["exists"] is False and body["problems"] == []
    assert body["settings"]["vale"]["binary"] == "vale"
    assert {r["id"] for r in body["rules"]} >= {"DOC001", "DOC002", "DOC003", "REQ001", "REQ002"}
    assert body["vale"]["available"] in (True, False)


def test_save_config_writes_the_repo_file_with_every_setting(client, repo_root):
    r = client.put("/lint/config", json={"glossary": {"Foo": ["foo"]}, "severities": {"DOC001": "error"}})
    assert r.status_code == 200, r.text
    saved = YAML(typ="safe").load((repo_root / ".reqtool" / "lint.yaml").read_text(encoding="utf-8"))
    assert saved["glossary"] == {"Foo": ["foo"]}
    assert saved["severities"]["DOC001"] == "error" and saved["severities"]["DOC002"] == "warning"
    assert "vale" in saved and "vague_terms" in saved
    assert client.post("/lint/text", json={"text": "use foo"}).json()["issues"][0]["severity"] == "error"


def test_invalid_config_is_422_and_unwritten(client, repo_root):
    assert client.put("/lint/config", json={"severities": {"DOC001": "loud"}}).status_code == 422
    assert client.put("/lint/config", json={"mystery": 1}).status_code == 422
    assert not (repo_root / ".reqtool" / "lint.yaml").exists()


def test_lint_text_and_item_and_all(client):
    issues = client.post("/lint/text", json={"text": "in order to"}).json()["issues"]
    assert [i["rule"] for i in issues] == ["DOC002"]
    uid = _make(client)
    item = client.get(f"/requirements/{uid}/lint").json()
    assert item["enabled"] and {i["rule"] for i in item["issues"]} >= {"DOC001", "DOC002", "REQ001"}
    everything = client.get("/lint").json()
    assert everything["summary"]["items_with_issues"] == 1 and everything["issues"]
    only_errors = client.get("/lint?severity=error").json()
    assert only_errors["issues"] == []
    assert client.get("/requirements/nope/lint").status_code == 404


def test_disabled_check_reports_nothing(client):
    _make(client)
    client.put("/lint/config", json={"enabled": False})
    assert client.get("/lint").json()["issues"] == []
    assert client.post("/lint/text", json={"text": "in order to"}).json() == {"enabled": False, "issues": []}


def test_validation_unchanged_unless_included(client):
    _make(client)
    base = client.get("/validate").json()
    assert not any(str(m).startswith("DOC") or "DOC002" in json.dumps(m) for m in base.get("warnings", []))
    client.put("/lint/config", json={"include_in_validation": True})
    with_lint = client.get("/validate").json()
    assert "DOC002" in json.dumps(with_lint)


def test_hand_edited_bad_file_does_not_break_the_tool(client, repo_root):
    (repo_root / ".reqtool" / "lint.yaml").write_text("severities:\n  DOC001: loud\n", encoding="utf-8")
    body = client.get("/lint/config").json()
    assert body["problems"]
    assert client.post("/lint/text", json={"text": "in order to"}).status_code == 200


def test_cli_exit_codes(client, repo_root):
    _make(client)
    run = lambda *a: CliRunner().invoke(cli, ["lint", "--repo", str(repo_root), *a])  # noqa: E731
    out = run("--fail-on", "never")
    assert out.exit_code == 0 and "DOC002" in out.output
    assert run("--fail-on", "warning").exit_code == 1
    assert run("--fail-on", "error").exit_code == 0
    data = json.loads(run("--fail-on", "never", "--format", "json").output)
    assert data["summary"]["issues"] >= 3


def test_changing_the_lint_file_does_not_reload_the_store(client_with_store, repo_root, monkeypatch):
    _, store = client_with_store
    loads = []
    monkeypatch.setattr(store, "load", lambda *a, **k: loads.append(1))
    store.reload_file(repo_root / ".reqtool" / "lint.yaml")
    assert loads == []
    store.reload_file(repo_root / ".reqtool" / "hierarchy.yaml")
    assert loads == [1]  # the workflow file still reloads
