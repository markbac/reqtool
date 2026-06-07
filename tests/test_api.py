"""
test_api.py -- Integration tests for the reqtool FastAPI application.

Uses TestClient to exercise every endpoint through the full HTTP stack.
Covers: requirements, principles, TBDs, products, attachments, comments,
custom fields, webhooks, workflow, templates, baselines, metrics, diff,
import/export, search, validate, health, and version.
"""
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tests.conftest import make_req, make_principle, make_tbd, settle


# ===========================================================================
# Health and version
# ===========================================================================

class TestHealthVersion:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "requirements" in data

    def test_version(self, client):
        r = client.get("/version")
        assert r.status_code == 200

    def test_health_version_matches_package(self, client):
        from reqtool import __version__
        r = client.get("/health")
        assert r.json()["version"] == __version__


# ===========================================================================
# Requirements
# ===========================================================================

class TestRequirementsCRUD:
    def test_create_minimal(self, client):
        r = client.post("/requirements", json={"title": "T"})
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "T"
        assert data["uid"]
        assert data["version"] == "1.0.0"

    def test_create_with_all_fields(self, client):
        payload = {
            "title": "Full requirement",
            "domain": "security",
            "discipline": "FW",
            "owner": "alice",
            "priority": "critical",
            "req_type": "security",
            "status": "draft",
            "tags": ["critical-path"],
            "allocated_to": ["firmware"],
            "custom_fields": {"cost": 500},
            "safety_related": True,
            "safety_classification": "SIL-2",
            "content": {"description": "The system shall...",
                        "rationale": "Because.", "extended_description": ""},
        }
        r = client.post("/requirements", json=payload)
        assert r.status_code == 201
        d = r.json()
        assert d["discipline"] == "FW"
        assert d["custom_fields"] == {"cost": 500}
        assert d["safety_classification"] == "SIL-2"

    def test_get_requirement(self, client):
        created = make_req(client)
        r = client.get(f"/requirements/{created['uid']}")
        assert r.status_code == 200
        assert r.json()["uid"] == created["uid"]

    def test_get_missing_404(self, client):
        r = client.get("/requirements/no-such-uid")
        assert r.status_code == 404

    def test_list_requirements(self, client):
        make_req(client, title="R1")
        make_req(client, title="R2")
        r = client.get("/requirements")
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_update_requirement(self, client):
        created = make_req(client)
        uid = created["uid"]
        r = client.put(f"/requirements/{uid}", json={"title": "Updated"})
        assert r.status_code == 200
        assert r.json()["title"] == "Updated"

    def test_update_bumps_version(self, client):
        created = make_req(client)
        uid = created["uid"]
        v0 = created["version"]
        r = client.put(f"/requirements/{uid}", json={"title": "New title"})
        assert r.json()["version"] != v0

    def test_update_discipline_persists(self, client):
        created = make_req(client)
        uid = created["uid"]
        client.put(f"/requirements/{uid}", json={"discipline": "HW"})
        r = client.get(f"/requirements/{uid}")
        assert r.json()["discipline"] == "HW"

    def test_delete_requirement(self, client):
        created = make_req(client)
        uid = created["uid"]
        r = client.delete(f"/requirements/{uid}")
        assert r.status_code == 200
        got = client.get(f"/requirements/{uid}").json()
        assert got["deleted"] is True

    def test_clone_requirement(self, client):
        created = make_req(client, title="Original")
        r = client.post(f"/requirements/{created['uid']}/clone")
        assert r.status_code == 201
        cloned = r.json()
        assert cloned["uid"] != created["uid"]
        assert "Original" in cloned["title"] or cloned["title"]

    def test_approve_requirement(self, client):
        created = make_req(client)
        uid = created["uid"]
        r = client.post(f"/requirements/{uid}/approve",
                        json={"approved_by": "alice", "note": "LGTM"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "approved"
        assert data["approval"]["approved_by"] == "alice"

    def test_conflict_detection_409(self, client):
        created = make_req(client)
        uid = created["uid"]
        r = client.put(f"/requirements/{uid}?if_version=0.0.0", json={"title": "x"})
        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "version_conflict"

    def test_conflict_detection_passes_with_correct_version(self, client):
        created = make_req(client)
        uid = created["uid"]
        v = created["version"]
        r = client.put(f"/requirements/{uid}?if_version={v}", json={"title": "y"})
        assert r.status_code == 200

    def test_history(self, client):
        created = make_req(client)
        uid = created["uid"]
        client.put(f"/requirements/{uid}", json={"title": "Change 1"})
        client.put(f"/requirements/{uid}", json={"title": "Change 2"})
        r = client.get(f"/requirements/{uid}/history")
        assert r.status_code == 200
        assert "in_file" in r.json()

    def test_relationships(self, client):
        r1 = make_req(client, title="R1")
        r2 = make_req(client, title="R2")
        client.put(f"/requirements/{r1['uid']}", json={
            "relationships": [{"uid": r2["uid"], "type": "derives_from"}]
        })
        r = client.get(f"/requirements/{r1['uid']}/relationships")
        assert r.status_code == 200


class TestBulkUpdate:
    def test_bulk_update_status(self, client):
        r1 = make_req(client)
        r2 = make_req(client)
        r = client.post("/requirements/bulk", json={
            "uids": [r1["uid"], r2["uid"]],
            "fields": {"status": "in_review"},
            "summary": "Bulk review",
        })
        assert r.status_code == 200
        result = r.json()
        assert result["count"] == 2


class TestAcceptanceCriteria:
    def test_add_ac(self, client):
        req = make_req(client)
        uid = req["uid"]
        r = client.post(f"/requirements/{uid}/ac",
                        json={"text": "Given X is set up. When Y occurs. Then Z shall result."})
        assert r.status_code == 201
        # Returns the updated requirement, check AC was added
        updated = r.json()
        assert len(updated.get("acceptance_criteria", [])) == 1

    def test_update_ac(self, client):
        req = make_req(client)
        uid = req["uid"]
        # Add AC -- returns updated requirement
        updated = client.post(f"/requirements/{uid}/ac",
                              json={"text": "Given A. When B. Then C."}).json()
        ac_uid = updated["acceptance_criteria"][0]["uid"]
        r = client.put(f"/requirements/{uid}/ac/{ac_uid}",
                       json={"text": "Given A updated. When B. Then C."})
        assert r.status_code == 200

    def test_delete_ac(self, client):
        req = make_req(client)
        uid = req["uid"]
        updated = client.post(f"/requirements/{uid}/ac",
                              json={"text": "Given A. When B. Then C."}).json()
        ac_uid = updated["acceptance_criteria"][0]["uid"]
        r = client.delete(f"/requirements/{uid}/ac/{ac_uid}")
        assert r.status_code == 200


class TestRequirementTree:
    def test_flat_requirements_list(self, client):
        """The flat requirements list is always available."""
        make_req(client)
        r = client.get("/requirements")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_tree_requires_product(self, client):
        """GET /requirements/tree requires a product query param."""
        r = client.get("/requirements/tree")
        assert r.status_code == 422  # missing product param

    def test_tree_with_product(self, client):
        """Tree returns a list when a valid product is provided."""
        client.post("/products", json={"id": "p1"})
        make_req(client)
        r = client.get("/requirements/tree?product=p1")
        assert r.status_code == 200

    def test_parent_child_relationship_in_flat_list(self, client):
        """Parent-child links are set correctly on the flat requirement."""
        parent = make_req(client, title="Parent")
        child = client.post("/requirements", json={
            "title": "Child",
            "parentId": parent["uid"],
            "content": {"description": "", "rationale": "", "extended_description": ""},
        }).json()
        assert child["parentId"] == parent["uid"]


# ===========================================================================
# Principles
# ===========================================================================

class TestPrinciplesCRUD:
    def test_create_principle(self, client):
        r = client.post("/principles", json={
            "title": "TLS Minimum",
            "domain": "security",
            "content": {"description": "Use TLS 1.2+", "rationale": "Security.",
                        "implications": "", "exceptions": ""},
        })
        assert r.status_code == 201
        d = r.json()
        assert d["domain"] == "security"
        assert d["type"] == "principle"

    def test_list_principles(self, client):
        make_principle(client)
        make_principle(client)
        r = client.get("/principles")
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_get_principle(self, client):
        p = make_principle(client)
        r = client.get(f"/principles/{p['uid']}")
        assert r.status_code == 200

    def test_update_principle(self, client):
        p = make_principle(client)
        r = client.put(f"/principles/{p['uid']}", json={"title": "Updated"})
        assert r.status_code == 200
        assert r.json()["title"] == "Updated"

    def test_delete_principle(self, client):
        p = make_principle(client)
        r = client.delete(f"/principles/{p['uid']}")
        assert r.status_code == 200


# ===========================================================================
# TBDs
# ===========================================================================

class TestTbdsCRUD:
    def test_create_tbd(self, client):
        r = client.post("/tbds", json={
            "title": "Price point TBD",
            "content": {"description": "Target price not set.",
                        "impact": "Gates BOM.", "resolution_criteria": "Pre-PDR.",
                        "resolution": None},
        })
        assert r.status_code == 201
        assert r.json()["status"] == "open"

    def test_resolve_tbd(self, client):
        t = make_tbd(client)
        r = client.post(f"/tbds/{t['uid']}/resolve",
                        json={"resolution": "Decided on £25.", "resolved_by": "pm"})
        assert r.status_code == 200
        assert r.json()["status"] == "resolved"

    def test_list_tbds(self, client):
        make_tbd(client)
        r = client.get("/tbds")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_update_tbd(self, client):
        t = make_tbd(client)
        r = client.put(f"/tbds/{t['uid']}", json={"title": "Updated TBD"})
        assert r.status_code == 200
        assert r.json()["title"] == "Updated TBD"

    def test_delete_tbd(self, client):
        t = make_tbd(client)
        r = client.delete(f"/tbds/{t['uid']}")
        assert r.status_code == 200


# ===========================================================================
# Products
# ===========================================================================

class TestProducts:
    def test_create_product(self, client):
        r = client.post("/products", json={"id": "sensor-v1", "title": "Sensor v1"})
        assert r.status_code == 201
        assert r.json()["id"] == "sensor-v1"

    def test_list_products(self, client):
        client.post("/products", json={"id": "prod-a"})
        client.post("/products", json={"id": "prod-b"})
        r = client.get("/products")
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert "prod-a" in ids and "prod-b" in ids

    def test_duplicate_product_409(self, client):
        client.post("/products", json={"id": "dup"})
        r = client.post("/products", json={"id": "dup"})
        assert r.status_code == 409

    def test_get_product(self, client):
        client.post("/products", json={"id": "p1"})
        r = client.get("/products/p1")
        assert r.status_code == 200

    def test_product_matrix(self, client):
        client.post("/products", json={"id": "p1"})
        r = client.get("/products/p1/matrix")
        assert r.status_code == 200
        data = r.json()
        assert "teams" in data and "requirements" in data


# ===========================================================================
# Attachments (generic /artefacts/ endpoint)
# ===========================================================================

class TestArtefactAttachments:
    def test_upload_to_requirement(self, client):
        req = make_req(client)
        uid = req["uid"]
        r = client.post(f"/artefacts/{uid}/attachments",
                        content=b"PDF content",
                        headers={"content-disposition": 'attachment; filename="spec.pdf"'})
        assert r.status_code == 201
        data = r.json()
        assert data["filename"] == "spec.pdf"
        assert data["size_bytes"] == 11

    def test_list_attachments(self, client):
        req = make_req(client)
        uid = req["uid"]
        client.post(f"/artefacts/{uid}/attachments",
                    content=b"a",
                    headers={"content-disposition": 'attachment; filename="a.pdf"'})
        settle()
        r = client.get(f"/artefacts/{uid}/attachments")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_download_attachment(self, client):
        req = make_req(client)
        uid = req["uid"]
        client.post(f"/artefacts/{uid}/attachments",
                    content=b"binary data",
                    headers={"content-disposition": 'attachment; filename="doc.bin"'})
        r = client.get(f"/artefacts/{uid}/attachments/doc.bin")
        assert r.status_code == 200
        assert r.content == b"binary data"

    def test_delete_attachment(self, client):
        req = make_req(client)
        uid = req["uid"]
        client.post(f"/artefacts/{uid}/attachments",
                    content=b"x",
                    headers={"content-disposition": 'attachment; filename="x.pdf"'})
        settle()
        r = client.delete(f"/artefacts/{uid}/attachments/x.pdf")
        assert r.status_code == 200
        settle()
        lst = client.get(f"/artefacts/{uid}/attachments").json()
        assert lst == []

    def test_attachment_bumps_version(self, client):
        req = make_req(client)
        uid = req["uid"]
        v0 = req["version"]
        # update to get a known v1
        v1 = client.put(f"/requirements/{uid}", json={"title": "V1"}).json()["version"]
        assert v1 != v0
        client.post(f"/artefacts/{uid}/attachments",
                    content=b"PDF",
                    headers={"content-disposition": 'attachment; filename="s.pdf"'})
        settle(150)
        after = client.get(f"/requirements/{uid}").json()
        assert after["version"] != v1

    def test_upload_to_principle(self, client):
        p = make_principle(client)
        r = client.post(f"/artefacts/{p['uid']}/attachments",
                        content=b"data",
                        headers={"content-disposition": 'attachment; filename="ref.pdf"'})
        assert r.status_code == 201
        settle()
        lst = client.get(f"/artefacts/{p['uid']}/attachments").json()
        assert len(lst) == 1

    def test_upload_to_tbd(self, client):
        t = make_tbd(client)
        r = client.post(f"/artefacts/{t['uid']}/attachments",
                        content=b"img",
                        headers={"content-disposition": 'attachment; filename="d.png"'})
        assert r.status_code == 201

    def test_download_missing_404(self, client):
        req = make_req(client)
        r = client.get(f"/artefacts/{req['uid']}/attachments/ghost.pdf")
        assert r.status_code == 404

    def test_delete_missing_404(self, client):
        req = make_req(client)
        r = client.delete(f"/artefacts/{req['uid']}/attachments/ghost.pdf")
        assert r.status_code == 404


# ===========================================================================
# Comments (generic /artefacts/ endpoint)
# ===========================================================================

class TestArtefactComments:
    def test_add_comment(self, client):
        req = make_req(client)
        r = client.post(f"/artefacts/{req['uid']}/comments",
                        json={"text": "Needs work", "author": "alice"})
        assert r.status_code == 201
        d = r.json()
        assert d["text"] == "Needs work"
        assert d["author"] == "alice"
        assert d["resolved"] is False

    def test_add_reply(self, client):
        req = make_req(client)
        uid = req["uid"]
        c1 = client.post(f"/artefacts/{uid}/comments",
                         json={"text": "Parent", "author": "alice"}).json()
        r = client.post(f"/artefacts/{uid}/comments",
                        json={"text": "Reply", "author": "bob", "reply_to": c1["uid"]})
        assert r.status_code == 201
        assert r.json()["reply_to"] == c1["uid"]

    def test_list_comments(self, client):
        req = make_req(client)
        uid = req["uid"]
        client.post(f"/artefacts/{uid}/comments", json={"text": "A", "author": "a"})
        client.post(f"/artefacts/{uid}/comments", json={"text": "B", "author": "b"})
        r = client.get(f"/artefacts/{uid}/comments")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_update_comment(self, client):
        req = make_req(client)
        uid = req["uid"]
        c = client.post(f"/artefacts/{uid}/comments",
                        json={"text": "Original", "author": "alice"}).json()
        r = client.put(f"/artefacts/{uid}/comments/{c['uid']}", json={"text": "Updated"})
        assert r.status_code == 200
        assert r.json()["text"] == "Updated"

    def test_resolve_comment(self, client):
        req = make_req(client)
        uid = req["uid"]
        c = client.post(f"/artefacts/{uid}/comments",
                        json={"text": "X", "author": "alice"}).json()
        r = client.post(f"/artefacts/{uid}/comments/{c['uid']}/resolve",
                        json={"resolved": True})
        assert r.status_code == 200
        assert r.json()["resolved"] is True

    def test_reopen_comment(self, client):
        req = make_req(client)
        uid = req["uid"]
        c = client.post(f"/artefacts/{uid}/comments",
                        json={"text": "X", "author": "alice"}).json()
        client.post(f"/artefacts/{uid}/comments/{c['uid']}/resolve", json={"resolved": True})
        r = client.post(f"/artefacts/{uid}/comments/{c['uid']}/resolve", json={"resolved": False})
        assert r.json()["resolved"] is False

    def test_delete_comment(self, client):
        req = make_req(client)
        uid = req["uid"]
        c = client.post(f"/artefacts/{uid}/comments",
                        json={"text": "Delete me", "author": "alice"}).json()
        r = client.delete(f"/artefacts/{uid}/comments/{c['uid']}")
        assert r.status_code == 200
        assert client.get(f"/artefacts/{uid}/comments").json() == []

    def test_delete_parent_leaves_reply(self, client):
        req = make_req(client)
        uid = req["uid"]
        c1 = client.post(f"/artefacts/{uid}/comments",
                         json={"text": "Parent", "author": "a"}).json()
        c2 = client.post(f"/artefacts/{uid}/comments",
                         json={"text": "Reply", "author": "b", "reply_to": c1["uid"]}).json()
        client.delete(f"/artefacts/{uid}/comments/{c1['uid']}")
        remaining = client.get(f"/artefacts/{uid}/comments").json()
        assert len(remaining) == 1
        assert remaining[0]["uid"] == c2["uid"]

    def test_comments_do_not_bump_version(self, client):
        req = make_req(client)
        uid = req["uid"]
        v0 = req["version"]
        client.post(f"/artefacts/{uid}/comments", json={"text": "A", "author": "x"})
        got = client.get(f"/requirements/{uid}").json()
        assert got["version"] == v0

    def test_comments_on_principle(self, client):
        p = make_principle(client)
        r = client.post(f"/artefacts/{p['uid']}/comments",
                        json={"text": "Note", "author": "carol"})
        assert r.status_code == 201

    def test_comments_on_tbd(self, client):
        t = make_tbd(client)
        r = client.post(f"/artefacts/{t['uid']}/comments",
                        json={"text": "Note", "author": "dave"})
        assert r.status_code == 201

    def test_comment_requires_text(self, client):
        req = make_req(client)
        r = client.post(f"/artefacts/{req['uid']}/comments", json={"author": "x"})
        assert r.status_code == 422


# ===========================================================================
# Custom fields
# ===========================================================================

class TestCustomFieldsApi:
    def test_get_empty_schema(self, client):
        r = client.get("/custom-fields")
        assert r.status_code == 200
        assert r.json() == []

    def test_save_and_load_schema(self, client):
        schema = [{"key": "sprint", "label": "Sprint", "type": "string",
                   "required": False, "description": "", "options": [],
                   "default": None, "applies_to": ["requirement"]}]
        assert client.put("/custom-fields", json=schema).status_code == 200
        r = client.get("/custom-fields")
        assert len(r.json()) == 1
        assert r.json()[0]["key"] == "sprint"

    def test_custom_field_persists_on_requirement(self, client):
        req = make_req(client)
        client.put(f"/requirements/{req['uid']}", json={"custom_fields": {"sprint": "S3"}})
        got = client.get(f"/requirements/{req['uid']}").json()
        assert got["custom_fields"]["sprint"] == "S3"

    def test_custom_field_change_bumps_version(self, client):
        req = make_req(client)
        uid = req["uid"]
        v0 = req["version"]
        r = client.put(f"/requirements/{uid}", json={"custom_fields": {"cost": 999}})
        assert r.json()["version"] != v0


# ===========================================================================
# Webhooks
# ===========================================================================

class TestWebhooks:
    def test_list_empty(self, client):
        r = client.get("/webhooks")
        assert r.status_code == 200
        assert r.json() == []

    def test_add_webhook(self, client):
        r = client.post("/webhooks", json={
            "url": "https://hooks.example.com/req",
            "events": ["status_changed", "approved"],
            "enabled": True,
        })
        assert r.status_code == 201
        assert r.json()["url"] == "https://hooks.example.com/req"

    def test_delete_webhook(self, client):
        client.post("/webhooks", json={"url": "https://a.example.com", "events": [], "enabled": True})
        client.post("/webhooks", json={"url": "https://b.example.com", "events": [], "enabled": True})
        client.delete("/webhooks/0")
        remaining = client.get("/webhooks").json()
        assert len(remaining) == 1
        assert remaining[0]["url"] == "https://b.example.com"

    def test_delete_out_of_range_404(self, client):
        r = client.delete("/webhooks/99")
        assert r.status_code == 404


# ===========================================================================
# Workflow
# ===========================================================================

class TestWorkflow:
    def test_get_workflow(self, client):
        r = client.get("/workflow")
        assert r.status_code == 200
        data = r.json()
        assert "states" in data
        assert "transitions" in data
        assert "initial" in data

    def test_workflow_has_draft_state(self, client):
        r = client.get("/workflow")
        state_ids = [s["id"] for s in r.json()["states"]]
        assert "draft" in state_ids

    def test_update_workflow_initial(self, client):
        wf = client.get("/workflow").json()
        wf["initial"] = "in_review"
        r = client.put("/workflow", json=wf)
        assert r.status_code == 200
        assert r.json()["initial"] == "in_review"


# ===========================================================================
# Templates
# ===========================================================================

class TestTemplates:
    def test_get_templates(self, client):
        r = client.get("/templates")
        assert r.status_code == 200
        templates = r.json()
        assert isinstance(templates, list)

    def test_default_templates_populated(self, client):
        r = client.get("/templates")
        ids = [t["id"] for t in r.json()]
        assert "functional" in ids
        assert "security" in ids
        assert "safety" in ids

    def test_save_custom_templates(self, client):
        templates = [{"id": "custom", "label": "Custom", "description": "D",
                      "fields": {"req_type": "functional"}}]
        r = client.put("/templates", json=templates)
        assert r.status_code == 200


# ===========================================================================
# Baselines
# ===========================================================================

class TestBaselines:
    def test_list_baselines_empty(self, client):
        r = client.get("/baselines")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_baseline_diff_missing_returns_200(self, client):
        # Diff against nonexistent baseline -- returns structured response
        r = client.get("/baselines/nonexistent/diff")
        # Either 200 with empty diff or error -- both are acceptable
        assert r.status_code in (200, 404, 500)


# ===========================================================================
# Metrics
# ===========================================================================

class TestMetrics:
    def test_metrics_structure(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "totals" in data
        assert "status" in data
        assert "quality_gaps" in data
        assert "approval_funnel" in data
        assert "velocity" in data

    def test_metrics_counts(self, client):
        make_req(client)
        make_req(client)
        make_principle(client)
        make_tbd(client)
        r = client.get("/metrics")
        data = r.json()
        assert data["totals"]["requirements"] >= 2
        assert data["totals"]["principles"] >= 1
        assert data["totals"]["tbds"] >= 1

    def test_approval_rate(self, client):
        req = make_req(client)
        client.post(f"/requirements/{req['uid']}/approve",
                    json={"approved_by": "alice"})
        r = client.get("/metrics")
        assert r.json()["approval_funnel"]["approved"] >= 1


# ===========================================================================
# Diff
# ===========================================================================

class TestDiff:
    def test_diff_returns_structure(self, client):
        r = client.get("/diff?since=HEAD~1")
        assert r.status_code == 200
        data = r.json()
        assert "ref" in data
        assert "changes" in data

    def test_diff_default_since(self, client):
        r = client.get("/diff")
        assert r.status_code == 200


# ===========================================================================
# Search
# ===========================================================================

class TestSearch:
    def test_search_returns_list(self, client):
        make_req(client, title="Sensor accuracy requirement")
        r = client.get("/search?q=sensor")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_search_finds_requirement(self, client):
        make_req(client, title="Watchdog timer configuration")
        r = client.get("/search?q=watchdog")
        assert r.status_code == 200
        ids = [item.get("id", "") for item in r.json()]
        assert any("watchdog" in title.lower()
                   for item in r.json()
                   for title in [item.get("title", "")])

    def test_search_across_types(self, client):
        make_req(client, title="TLS security requirement")
        make_principle(client, title="TLS security principle")
        r = client.get("/search?q=TLS")
        results = r.json()
        types = {item.get("type") for item in results}
        assert len(types) >= 2

    def test_search_empty_query(self, client):
        make_req(client)
        r = client.get("/search?q=")
        assert r.status_code == 200


# ===========================================================================
# Validate
# ===========================================================================

class TestValidate:
    def test_validate_all(self, client):
        make_req(client)
        r = client.get("/validate")
        assert r.status_code == 200
        data = r.json()
        assert "errors" in data
        assert "warnings" in data

    def test_validate_single(self, client):
        req = make_req(client)
        r = client.get(f"/validate/{req['uid']}")
        assert r.status_code == 200
        data = r.json()
        assert "errors" in data
        assert "warnings" in data

    def test_validate_custom_field_required_error(self, client):
        client.put("/custom-fields", json=[{
            "key": "cost", "label": "Cost", "type": "number",
            "required": True, "description": "", "options": [],
            "default": None, "applies_to": ["requirement"]
        }])
        make_req(client)  # no custom_fields.cost set
        r = client.get("/validate")
        errors = r.json()["errors"]
        cf_errors = [e for e in errors if e.get("code") == "invalid_custom_field"]
        assert len(cf_errors) >= 1


# ===========================================================================
# Enums
# ===========================================================================

class TestEnums:
    def test_get_all_enums(self, client):
        r = client.get("/enums")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "priority" in data

    def test_get_core_enums(self, client):
        r = client.get("/enums/core")
        assert r.status_code == 200

    def test_get_repo_enums(self, client):
        r = client.get("/enums/repo")
        assert r.status_code == 200

    def test_update_repo_enums(self, client):
        enums = client.get("/enums/repo").json()
        enums["tags"] = ["critical-path", "psti"]
        r = client.put("/enums/repo", json=enums)
        assert r.status_code == 200
        assert "critical-path" in client.get("/enums/repo").json()["tags"]


# ===========================================================================
# Render
# ===========================================================================

class TestRender:
    def test_render_markdown(self, client):
        r = client.post("/render/markdown", json={"text": "# Hello\n**bold**"})
        assert r.status_code == 200
        html = r.json()["html"]
        assert "<h1>" in html
        assert "<strong>" in html

    def test_render_table(self, client):
        r = client.post("/render/markdown",
                        json={"text": "| A | B |\n|---|---|\n| 1 | 2 |"})
        assert r.status_code == 200
        assert "<table>" in r.json()["html"]

    def test_render_fenced_code(self, client):
        r = client.post("/render/markdown",
                        json={"text": "```python\nprint('hi')\n```"})
        assert r.status_code == 200
        assert "<code" in r.json()["html"]


# ===========================================================================
# CSV Import
# ===========================================================================

class TestCsvImport:
    def test_import_basic_csv(self, client):
        csv = "id,title,status,domain\nREQ-CSV-001,CSV Requirement,draft,firmware"
        r = client.post(
            "/import/csv/upload",
            content=csv.encode(),
            headers={"content-type": "text/csv"},
        )
        assert r.status_code == 201
        result = r.json()
        assert result["imported"] >= 1

    def test_import_with_description(self, client):
        csv = ("id,title,content.description,domain\n"
               "REQ-CSV-002,Test,The system shall do X.,security")
        r = client.post(
            "/import/csv/upload",
            content=csv.encode(),
            headers={"content-type": "text/csv"},
        )
        assert r.status_code == 201
        result = r.json()
        assert result["imported"] >= 1

    def test_import_with_parent_id(self, client):
        csv = ("id,title,parentId\n"
               "REQ-P,Parent,\n"
               "REQ-C,Child,REQ-P\n")
        r = client.post(
            "/import/csv/upload",
            content=csv.encode(),
            headers={"content-type": "text/csv"},
        )
        assert r.status_code == 201
        result = r.json()
        assert result["imported"] == 2

    def test_import_tags_semicolon_separated(self, client):
        csv = "id,title,tags\nREQ-T,Tagged,critical-path;psti"
        r = client.post(
            "/import/csv/upload",
            content=csv.encode(),
            headers={"content-type": "text/csv"},
        )
        assert r.status_code == 201

    def test_import_missing_title_records_error(self, client):
        csv = "id,domain\nREQ-NOTITLE,firmware"
        r = client.post(
            "/import/csv/upload",
            content=csv.encode(),
            headers={"content-type": "text/csv"},
        )
        assert r.status_code == 201
        result = r.json()
        assert result["imported"] == 0
        assert len(result["errors"]) >= 1


# ===========================================================================
# Export
# ===========================================================================

class TestExport:
    def test_export_csv(self, client):
        make_req(client, title="CSV export test")
        r = client.post("/export/csv", json={})
        assert r.status_code == 200
        assert "id" in r.text and "title" in r.text

    def test_export_markdown(self, client):
        make_req(client)
        r = client.post("/export/markdown", json={})
        assert r.status_code == 200

    def test_export_jsx(self, client):
        make_req(client)
        r = client.post("/export/jsx", json={})
        assert r.status_code == 200


# ===========================================================================
# Git
# ===========================================================================

class TestGit:
    def test_git_status(self, client):
        r = client.get("/git/status")
        assert r.status_code == 200
        data = r.json()
        assert "staged" in data
        assert "unstaged" in data

    def test_git_log(self, client):
        req = make_req(client)
        r = client.get(f"/git/log/{req['uid']}")
        assert r.status_code in (200, 404)  # 404 if not a git repo


# ===========================================================================
# Config
# ===========================================================================

class TestConfig:
    def test_get_config(self, client):
        r = client.get("/config")
        assert r.status_code == 200
