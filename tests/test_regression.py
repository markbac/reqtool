"""
test_regression.py -- End-to-end regression tests for reqtool v0.2.0.

These tests cover the full stack from API to store to disk for every
major feature area. They are the canonical "is it all still working?"
suite -- fast enough to run on every commit.
"""
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tests.conftest import make_req, make_principle, make_tbd, settle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(repo_root: Path) -> TestClient:
    from reqtool.api import create_app
    return TestClient(create_app(repo_root), raise_server_exceptions=True)


# ===========================================================================
# Package version
# ===========================================================================

class TestPackageVersion:
    def test_init_version_matches_pyproject(self):
        import tomllib
        from reqtool import __version__
        with open(Path(__file__).parent.parent / "pyproject.toml", "rb") as f:
            pj = tomllib.load(f)
        assert pj["project"]["version"] == __version__

    def test_health_reports_correct_version(self, client):
        from reqtool import __version__
        r = client.get("/health")
        assert r.json()["version"] == __version__

    def test_version_endpoint(self, client):
        r = client.get("/version")
        assert r.status_code == 200


# ===========================================================================
# Discipline and new fields on create
# ===========================================================================

class TestNewFields:
    def test_discipline_on_create(self, client):
        r = client.post("/requirements", json={
            "title": "T", "discipline": "FW", "domain": "firmware"
        })
        assert r.status_code == 201
        assert r.json()["discipline"] == "FW"

    def test_discipline_on_update(self, client):
        req = make_req(client)
        client.put(f"/requirements/{req['uid']}", json={"discipline": "HW"})
        got = client.get(f"/requirements/{req['uid']}").json()
        assert got["discipline"] == "HW"

    def test_custom_fields_on_create(self, client):
        r = client.post("/requirements", json={
            "title": "T", "custom_fields": {"sprint": "S3", "cost": 200}
        })
        assert r.status_code == 201
        assert r.json()["custom_fields"] == {"sprint": "S3", "cost": 200}

    def test_custom_fields_update_bumps_version(self, client):
        req = make_req(client)
        uid = req["uid"]
        v0 = req["version"]
        r = client.put(f"/requirements/{uid}", json={"custom_fields": {"cost": 999}})
        assert r.json()["version"] != v0

    def test_attachments_field_exists_on_create(self, client):
        req = make_req(client)
        assert "attachments" in req
        assert req["attachments"] == []


# ===========================================================================
# Version bumping
# ===========================================================================

class TestVersionBumping:
    def test_title_change_bumps_version(self, client):
        req = make_req(client)
        v0 = req["version"]
        v1 = client.put(f"/requirements/{req['uid']}", json={"title": "New"}).json()["version"]
        assert v1 != v0

    def test_domain_change_bumps_version(self, client):
        req = make_req(client, domain="firmware")
        v0 = req["version"]
        v1 = client.put(f"/requirements/{req['uid']}", json={"domain": "security"}).json()["version"]
        assert v1 != v0

    def test_owner_change_bumps_version(self, client):
        req = make_req(client, owner="alice")
        v0 = req["version"]
        v1 = client.put(f"/requirements/{req['uid']}", json={"owner": "bob"}).json()["version"]
        assert v1 != v0

    def test_tags_change_bumps_version(self, client):
        req = make_req(client, tags=["a"])
        v0 = req["version"]
        v1 = client.put(f"/requirements/{req['uid']}", json={"tags": ["a", "b"]}).json()["version"]
        assert v1 != v0

    def test_no_change_no_version_bump(self, client):
        req = make_req(client, title="Stable")
        v0 = req["version"]
        v1 = client.put(f"/requirements/{req['uid']}", json={"title": "Stable"}).json()["version"]
        assert v1 == v0

    def test_attachment_upload_bumps_version(self, client):
        req = make_req(client)
        uid = req["uid"]
        v0 = req["version"]
        # make a known v1
        v1 = client.put(f"/requirements/{uid}", json={"title": "V1"}).json()["version"]
        client.post(f"/artefacts/{uid}/attachments", content=b"PDF",
                    headers={"content-disposition": 'attachment; filename="s.pdf"'})
        settle(150)
        after = client.get(f"/requirements/{uid}").json()
        assert after["version"] != v1


# ===========================================================================
# Concurrent edit detection
# ===========================================================================

class TestConcurrentEdits:
    def test_conflict_wrong_version(self, client):
        req = make_req(client)
        r = client.put(f"/requirements/{req['uid']}?if_version=0.0.0",
                       json={"title": "Conflict"})
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["error"] == "version_conflict"
        assert "current_version" in detail
        assert "your_version" in detail

    def test_correct_version_succeeds(self, client):
        req = make_req(client)
        v = req["version"]
        r = client.put(f"/requirements/{req['uid']}?if_version={v}",
                       json={"title": "OK"})
        assert r.status_code == 200

    def test_no_version_check_always_succeeds(self, client):
        req = make_req(client)
        r = client.put(f"/requirements/{req['uid']}", json={"title": "X"})
        assert r.status_code == 200


# ===========================================================================
# Attachments full flow
# ===========================================================================

class TestAttachmentsFullFlow:
    def test_requirement_upload_list_download_delete(self, client):
        req = make_req(client)
        uid = req["uid"]

        # Upload
        up = client.post(f"/artefacts/{uid}/attachments",
                         content=b"PDF content here",
                         headers={"content-disposition": 'attachment; filename="spec.pdf"'})
        assert up.status_code == 201
        rec = up.json()
        assert rec["filename"] == "spec.pdf"
        assert rec["size_bytes"] == 16
        assert rec["sha256"].startswith("sha256:")

        # List
        settle(120)
        lst = client.get(f"/artefacts/{uid}/attachments").json()
        assert len(lst) == 1
        assert lst[0]["filename"] == "spec.pdf"

        # Download
        dl = client.get(f"/artefacts/{uid}/attachments/spec.pdf")
        assert dl.status_code == 200
        assert dl.content == b"PDF content here"

        # Delete
        d = client.delete(f"/artefacts/{uid}/attachments/spec.pdf")
        assert d.status_code == 200

        settle(120)
        assert client.get(f"/artefacts/{uid}/attachments").json() == []

    def test_principle_attachment(self, client):
        p = make_principle(client)
        up = client.post(f"/artefacts/{p['uid']}/attachments",
                         content=b"Ref document",
                         headers={"content-disposition": 'attachment; filename="ref.docx"'})
        assert up.status_code == 201
        settle()
        lst = client.get(f"/artefacts/{p['uid']}/attachments").json()
        assert len(lst) == 1

    def test_tbd_attachment(self, client):
        t = make_tbd(client)
        up = client.post(f"/artefacts/{t['uid']}/attachments",
                         content=b"Diagram",
                         headers={"content-disposition": 'attachment; filename="d.png"'})
        assert up.status_code == 201


# ===========================================================================
# Comments full flow
# ===========================================================================

class TestCommentsFullFlow:
    def test_requirement_full_comment_lifecycle(self, client):
        req = make_req(client)
        uid = req["uid"]

        # Add top-level comment
        c1 = client.post(f"/artefacts/{uid}/comments",
                         json={"text": "This needs clarification.", "author": "alice"}).json()
        assert c1["text"] == "This needs clarification."
        assert not c1["resolved"]

        # Add reply
        c2 = client.post(f"/artefacts/{uid}/comments",
                         json={"text": "Agreed, see ICD.", "author": "bob",
                               "reply_to": c1["uid"]}).json()
        assert c2["reply_to"] == c1["uid"]

        # List -- 2 items
        lst = client.get(f"/artefacts/{uid}/comments").json()
        assert len(lst) == 2

        # Edit c1
        upd = client.put(f"/artefacts/{uid}/comments/{c1['uid']}",
                         json={"text": "Updated clarification."})
        assert upd.json()["text"] == "Updated clarification."
        assert upd.json()["updated_at"] is not None

        # Resolve c1
        res = client.post(f"/artefacts/{uid}/comments/{c1['uid']}/resolve",
                          json={"resolved": True})
        assert res.json()["resolved"] is True

        # Reopen c1
        reopen = client.post(f"/artefacts/{uid}/comments/{c1['uid']}/resolve",
                              json={"resolved": False})
        assert reopen.json()["resolved"] is False

        # Delete c1 -- c2 (reply) persists
        client.delete(f"/artefacts/{uid}/comments/{c1['uid']}")
        remaining = client.get(f"/artefacts/{uid}/comments").json()
        assert len(remaining) == 1
        assert remaining[0]["uid"] == c2["uid"]

    def test_comments_do_not_affect_version(self, client):
        req = make_req(client)
        uid = req["uid"]
        v0 = req["version"]
        client.post(f"/artefacts/{uid}/comments", json={"text": "A comment", "author": "x"})
        assert client.get(f"/requirements/{uid}").json()["version"] == v0


# ===========================================================================
# Custom fields full flow
# ===========================================================================

class TestCustomFieldsFullFlow:
    def test_define_use_and_validate(self, client, repo_root):
        # Define schema
        schema = [
            {"key": "sprint", "label": "Sprint", "type": "string",
             "required": False, "description": "", "options": [],
             "default": None, "applies_to": ["requirement"]},
            {"key": "cost_k", "label": "Cost (£k)", "type": "number",
             "required": True, "description": "", "options": [],
             "default": None, "applies_to": ["requirement"]},
            {"key": "tier", "label": "Tier", "type": "select",
             "required": False, "description": "",
             "options": ["gold", "silver", "bronze"],
             "default": None, "applies_to": ["requirement"]},
        ]
        assert client.put("/custom-fields", json=schema).status_code == 200

        # Schema round-trips
        loaded = client.get("/custom-fields").json()
        assert len(loaded) == 3
        keys = [f["key"] for f in loaded]
        assert "sprint" in keys and "cost_k" in keys and "tier" in keys

        # Requirement with valid custom fields
        req = client.post("/requirements", json={
            "title": "CF test",
            "custom_fields": {"sprint": "S3", "cost_k": 12.5, "tier": "gold"}
        }).json()
        assert req["custom_fields"]["tier"] == "gold"

        # Validate -- no errors for valid values
        result = client.get(f"/validate/{req['uid']}").json()
        cf_errors = [e for e in result["errors"] if e.get("code") == "invalid_custom_field"]
        assert cf_errors == []

        # Requirement with missing required field
        bad_req = client.post("/requirements", json={"title": "No cost"}).json()
        result2 = client.get("/validate").json()
        cf_errors2 = [e for e in result2["errors"] if e.get("code") == "invalid_custom_field"]
        assert len(cf_errors2) >= 1


# ===========================================================================
# Webhooks
# ===========================================================================

class TestWebhooksFullFlow:
    def test_add_list_delete(self, client):
        # Initially empty
        assert client.get("/webhooks").json() == []

        # Add two webhooks
        client.post("/webhooks", json={"url": "https://a.example.com",
                                        "events": ["status_changed"], "enabled": True})
        client.post("/webhooks", json={"url": "https://b.example.com",
                                        "events": ["approved"], "enabled": False})
        hooks = client.get("/webhooks").json()
        assert len(hooks) == 2

        # Delete first
        client.delete("/webhooks/0")
        remaining = client.get("/webhooks").json()
        assert len(remaining) == 1
        assert remaining[0]["url"] == "https://b.example.com"

    def test_out_of_range_delete(self, client):
        r = client.delete("/webhooks/0")
        assert r.status_code == 404


# ===========================================================================
# Markdown rendering
# ===========================================================================

class TestMarkdownRendering:
    def test_headings(self, client):
        r = client.post("/render/markdown", json={"text": "# H1\n## H2"})
        html = r.json()["html"]
        assert "<h1>" in html and "<h2>" in html

    def test_bold_italic(self, client):
        r = client.post("/render/markdown", json={"text": "**bold** and _italic_"})
        html = r.json()["html"]
        assert "<strong>" in html
        assert "<em>" in html

    def test_table(self, client):
        r = client.post("/render/markdown",
                        json={"text": "| A | B |\n|---|---|\n| 1 | 2 |"})
        assert "<table>" in r.json()["html"]

    def test_fenced_code(self, client):
        r = client.post("/render/markdown",
                        json={"text": "```python\nx = 1\n```"})
        assert "<code" in r.json()["html"]

    def test_bullet_list(self, client):
        r = client.post("/render/markdown", json={"text": "- a\n- b\n- c"})
        assert "<li>" in r.json()["html"]

    def test_empty_text(self, client):
        r = client.post("/render/markdown", json={"text": ""})
        assert r.status_code == 200
        assert isinstance(r.json()["html"], str)


# ===========================================================================
# Metrics
# ===========================================================================

class TestMetricsFullFlow:
    def test_metrics_after_creates(self, client):
        make_req(client)
        make_req(client)
        make_principle(client)
        make_tbd(client)
        r = client.get("/metrics").json()
        assert r["totals"]["requirements"] >= 2
        assert r["totals"]["principles"] >= 1
        assert r["totals"]["tbds"] >= 1

    def test_approval_rate_calculation(self, client):
        r1 = make_req(client)
        r2 = make_req(client)
        client.post(f"/requirements/{r1['uid']}/approve", json={"approved_by": "alice"})
        metrics = client.get("/metrics").json()
        assert metrics["approval_funnel"]["approved"] >= 1

    def test_quality_gaps_populated(self, client):
        make_req(client)
        gaps = client.get("/metrics").json()["quality_gaps"]
        # At minimum these keys should exist
        assert "no_owner" in gaps
        assert "no_ac" in gaps
        assert "no_rationale" in gaps


# ===========================================================================
# CSV import
# ===========================================================================

class TestCsvImportRegression:
    def test_full_import(self, client):
        csv = "\n".join([
            "id,title,status,priority,domain,content.description,tags",
            "REQ-001,Temperature accuracy,draft,high,sensing,Shall measure to ±0.5°C,critical-path",
            "REQ-002,Battery life,draft,high,power,Shall operate for 12 months,",
            "REQ-003,Matter protocol,draft,high,comms,Shall implement Matter 1.x,",
        ])
        r = client.post("/import/csv/upload",
                        content=csv.encode(),
                        headers={"content-type": "text/csv"})
        assert r.status_code == 201
        result = r.json()
        assert result["imported"] == 3
        assert result["errors"] == []

    def test_import_missing_title_error(self, client):
        csv = "id,domain\nREQ-NT,firmware"
        r = client.post("/import/csv/upload",
                        content=csv.encode(),
                        headers={"content-type": "text/csv"})
        assert r.status_code == 201
        assert r.json()["imported"] == 0
        assert len(r.json()["errors"]) >= 1

    def test_import_with_parent_links(self, client):
        csv = "id,title,parentId\nREQ-P,Parent,\nREQ-C,Child,REQ-P"
        r = client.post("/import/csv/upload",
                        content=csv.encode(),
                        headers={"content-type": "text/csv"})
        assert r.status_code == 201
        assert r.json()["imported"] == 2


# ===========================================================================
# init defaults + principles domain coverage
# ===========================================================================

class TestInitDefaultsRegression:
    def test_principles_cover_8_domains(self):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.store import Store

        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(cli, ["init", "defaults", "--id", "x", "--title", "X"])
            assert result.exit_code == 0
            root = Path(td)
            s = Store(root)
            s.load()
            domains = {p.get("domain") for p in s.principles.values() if p.get("domain")}
            expected = {"business", "architecture", "security", "firmware",
                        "comms", "data", "process", "safety"}
            assert expected.issubset(domains), f"Missing domains: {expected - domains}"

    def test_workflow_states_in_config(self):
        from click.testing import CliRunner
        from reqtool.cli import cli
        from reqtool.fileio import load_yaml

        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "defaults", "--id", "x", "--title", "X"])
            cfg = load_yaml(Path(td) / ".reqtool" / "config.yaml")
            wf = cfg.get("workflow", {})
            assert "states" in wf
            state_ids = [s["id"] for s in wf["states"]]
            assert "draft" in state_ids
            assert "approved" in state_ids


# ===========================================================================
# Request model completeness
# ===========================================================================

class TestRequestModels:
    def test_create_model_has_all_fields(self):
        from reqtool.models import CreateRequirementRequest
        required = {"discipline", "custom_fields", "attachments", "domain",
                    "owner", "allocated_to", "tags", "safety_related",
                    "safety_classification", "verification_method"}
        actual = set(CreateRequirementRequest.model_fields.keys())
        missing = required - actual
        assert not missing, f"CreateRequirementRequest missing: {missing}"

    def test_update_model_has_all_fields(self):
        from reqtool.models import UpdateRequirementRequest
        required = {"discipline", "custom_fields", "attachments", "domain",
                    "owner", "allocated_to", "tags"}
        actual = set(UpdateRequirementRequest.model_fields.keys())
        missing = required - actual
        assert not missing, f"UpdateRequirementRequest missing: {missing}"
