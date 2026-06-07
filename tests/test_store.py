"""
test_store.py -- Unit tests for reqtool.store.Store.

Covers: create/read/update/delete for requirements, principles, TBDs;
versioning, hashing, history, attachments, comments, custom fields,
incremental reload, and search.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reqtool.store import Store
from reqtool.fileio import load_yaml, save_yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_req(store: Store, **kwargs) -> dict:
    base = {
        "id": "REQ-001",
        "title": "The system shall do X.",
        "content": {"description": "The system shall do X.",
                    "rationale": "Because.", "extended_description": ""},
    }
    base.update(kwargs)
    return store.create_requirement(base)


def _make_principle(store: Store, **kwargs) -> dict:
    base = {
        "id": "P-001",
        "title": "Test principle",
        "domain": "architecture",
        "content": {"description": "Desc.", "rationale": "R.",
                    "implications": "", "exceptions": ""},
    }
    base.update(kwargs)
    return store.create_principle(base)


def _make_tbd(store: Store, **kwargs) -> dict:
    base = {
        "id": "TBD-001",
        "title": "Unresolved item",
        "content": {"description": "Desc.", "impact": "High.",
                    "resolution_criteria": "When X.", "resolution": None},
    }
    base.update(kwargs)
    return store.create_tbd(base)


# ===========================================================================
# Store.load / init
# ===========================================================================

class TestStoreLoad:
    def test_empty_load(self, repo_root):
        s = Store(repo_root)
        s.load()
        assert s.requirements == {}
        assert s.principles == {}
        assert s.tbds == {}

    def test_load_persisted_requirements(self, store):
        _make_req(store)
        # Reload from disk
        s2 = Store(store.root)
        s2.load()
        assert len(s2.requirements) == 1

    def test_load_ignores_deleted(self, store):
        r = _make_req(store)
        store.delete_requirement(r["uid"])
        s2 = Store(store.root)
        s2.load()
        # Deleted items are loaded but flagged
        assert s2.requirements[r["uid"]]["deleted"] is True


# ===========================================================================
# Requirement CRUD
# ===========================================================================

class TestCreateRequirement:
    def test_basic_create(self, store):
        r = _make_req(store)
        assert r["uid"]
        assert r["title"] == "The system shall do X."
        assert r["version"] == "1.0.0"
        assert r["status"] == "draft"
        assert r["type"] == "requirement"

    def test_all_fields_set(self, store):
        r = store.create_requirement({
            "id": "REQ-X", "title": "T",
            "content": {"description": "D", "rationale": "", "extended_description": ""},
            "discipline": "FW",
            "domain": "firmware",
            "owner": "alice",
            "allocated_to": ["firmware", "hardware"],
            "tags": ["critical-path"],
            "priority": "critical",
            "req_type": "security",
            "custom_fields": {"cost": 1500},
            "safety_related": True,
            "safety_classification": "SIL-2",
        })
        assert r["discipline"] == "FW"
        assert r["domain"] == "firmware"
        assert r["owner"] == "alice"
        assert r["allocated_to"] == ["firmware", "hardware"]
        assert r["tags"] == ["critical-path"]
        assert r["custom_fields"] == {"cost": 1500}
        assert r["safety_related"] is True
        assert r["safety_classification"] == "SIL-2"

    def test_content_hash_set(self, store):
        r = _make_req(store)
        assert r["content_hash"].startswith("sha256:")

    def test_written_to_disk(self, store):
        r = _make_req(store)
        path = store.req_path(r["uid"])
        assert path.exists()
        on_disk = load_yaml(path)
        assert on_disk["uid"] == r["uid"]

    def test_in_memory_after_create(self, store):
        r = _make_req(store)
        assert r["uid"] in store.requirements


class TestGetRequirement:
    def test_get_existing(self, store):
        r = _make_req(store)
        got = store.get_requirement(r["uid"])
        assert got["uid"] == r["uid"]

    def test_get_missing_returns_none(self, store):
        assert store.get_requirement("no-such-uid") is None

    def test_returns_live_dict(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.requirements[uid]["_sentinel"] = True
        assert store.get_requirement(uid).get("_sentinel") is True


class TestUpdateRequirement:
    def test_title_change_bumps_patch_version(self, store):
        r = _make_req(store)
        uid = r["uid"]
        v0 = r["version"]
        updated = store.update_requirement(uid, {"title": "Updated title"})
        assert updated["version"] != v0
        assert updated["title"] == "Updated title"

    def test_no_change_no_version_bump(self, store):
        r = _make_req(store)
        uid = r["uid"]
        v0 = r["version"]
        # Update with same data
        store.update_requirement(uid, {"title": r["title"]})
        assert store.requirements[uid]["version"] == v0

    def test_minor_increment(self, store):
        r = _make_req(store)
        uid = r["uid"]
        updated = store.update_requirement(uid, {"title": "New"}, increment="minor")
        assert updated["version"] == "1.1.0"

    def test_major_increment(self, store):
        r = _make_req(store)
        uid = r["uid"]
        updated = store.update_requirement(uid, {"title": "New"}, increment="major")
        assert updated["version"] == "2.0.0"

    def test_history_appended(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.update_requirement(uid, {"title": "A"}, summary="First change")
        store.update_requirement(uid, {"title": "B"}, summary="Second change")
        hist = store.requirements[uid]["history"]
        assert len(hist) == 3  # initial + 2 updates
        assert hist[-1]["summary"] == "Second change"

    def test_discipline_persists(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.update_requirement(uid, {"discipline": "HW"})
        assert store.requirements[uid]["discipline"] == "HW"

    def test_custom_fields_update_bumps_version(self, store):
        r = _make_req(store, custom_fields={"cost": 100})
        uid = r["uid"]
        v0 = r["version"]
        store.update_requirement(uid, {"custom_fields": {"cost": 200}})
        assert store.requirements[uid]["version"] != v0
        assert store.requirements[uid]["custom_fields"]["cost"] == 200

    def test_written_to_disk(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.update_requirement(uid, {"title": "Disk test"})
        on_disk = load_yaml(store.req_path(uid))
        assert on_disk["title"] == "Disk test"

    def test_missing_uid_returns_none(self, store):
        assert store.update_requirement("no-such", {"title": "x"}) is None


class TestDeleteRequirement:
    def test_soft_delete(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.delete_requirement(uid)
        assert store.requirements[uid]["deleted"] is True

    def test_deleted_written_to_disk(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.delete_requirement(uid)
        on_disk = load_yaml(store.req_path(uid))
        assert on_disk["deleted"] is True


class TestVersioning:
    def test_content_hash_changes_with_title(self, store):
        r = _make_req(store)
        h0 = r["content_hash"]
        store.update_requirement(r["uid"], {"title": "Different title"})
        h1 = store.requirements[r["uid"]]["content_hash"]
        assert h0 != h1

    def test_content_hash_stable_without_change(self, store):
        r = _make_req(store)
        h0 = r["content_hash"]
        store.update_requirement(r["uid"], {"title": r["title"]})
        h1 = store.requirements[r["uid"]]["content_hash"]
        assert h0 == h1

    def test_attachment_change_bumps_version(self, store):
        r = _make_req(store)
        uid = r["uid"]
        v0 = r["version"]
        store.update_requirement(uid, {"attachments": [{"filename": "x.pdf", "size_bytes": 4}]})
        assert store.requirements[uid]["version"] != v0

    def test_domain_change_bumps_version(self, store):
        r = _make_req(store, domain="firmware")
        uid = r["uid"]
        v0 = r["version"]
        store.update_requirement(uid, {"domain": "security"})
        assert store.requirements[uid]["version"] != v0

    def test_tags_change_bumps_version(self, store):
        r = _make_req(store, tags=["a"])
        uid = r["uid"]
        v0 = r["version"]
        store.update_requirement(uid, {"tags": ["a", "b"]})
        assert store.requirements[uid]["version"] != v0


# ===========================================================================
# Principle CRUD
# ===========================================================================

class TestPrincipleCRUD:
    def test_create(self, store):
        p = _make_principle(store)
        assert p["uid"]
        assert p["domain"] == "architecture"
        assert p["version"] == "1.0.0"
        assert p["type"] == "principle"

    def test_attachments_field_initialised(self, store):
        p = _make_principle(store)
        assert "attachments" in p
        assert p["attachments"] == []

    def test_update(self, store):
        p = _make_principle(store)
        uid = p["uid"]
        v0 = p["version"]
        updated = store.update_principle(uid, {"title": "New title"})
        assert updated["title"] == "New title"
        assert updated["version"] != v0

    def test_delete(self, store):
        p = _make_principle(store)
        store.delete_principle(p["uid"])
        assert store.principles[p["uid"]]["deleted"] is True

    def test_written_to_disk(self, store):
        p = _make_principle(store)
        assert store.principle_path(p["uid"]).exists()


# ===========================================================================
# TBD CRUD
# ===========================================================================

class TestTbdCRUD:
    def test_create(self, store):
        t = _make_tbd(store)
        assert t["uid"]
        assert t["status"] == "open"
        assert t["type"] == "tbd"

    def test_attachments_field_initialised(self, store):
        t = _make_tbd(store)
        assert "attachments" in t
        assert t["attachments"] == []

    def test_update(self, store):
        t = _make_tbd(store)
        uid = t["uid"]
        updated = store.update_tbd(uid, {"title": "New"})
        assert updated["title"] == "New"

    def test_delete(self, store):
        t = _make_tbd(store)
        store.delete_tbd(t["uid"])
        assert store.tbds[t["uid"]]["deleted"] is True


# ===========================================================================
# Attachments
# ===========================================================================

class TestAttachments:
    def test_add_attachment_to_requirement(self, store):
        r = _make_req(store)
        uid = r["uid"]
        rec = store.add_attachment(uid, "spec.pdf", b"PDF content")
        assert rec["filename"] == "spec.pdf"
        assert rec["size_bytes"] == 11
        assert rec["sha256"].startswith("sha256:")

    def test_binary_written_after_yaml(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.add_attachment(uid, "file.pdf", b"data")
        binary = store.attachment_dir(uid) / "file.pdf"
        assert binary.exists()
        assert binary.read_bytes() == b"data"

    def test_attachment_version_bump(self, store):
        r = _make_req(store)
        uid = r["uid"]
        v0 = r["version"]
        store.add_attachment(uid, "x.pdf", b"x")
        assert store.requirements[uid]["version"] != v0

    def test_attachment_in_yaml(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.add_attachment(uid, "a.pdf", b"a")
        on_disk = load_yaml(store.req_path(uid))
        assert len(on_disk["attachments"]) == 1
        assert on_disk["attachments"][0]["filename"] == "a.pdf"

    def test_replace_same_filename(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.add_attachment(uid, "x.pdf", b"v1")
        store.add_attachment(uid, "x.pdf", b"v2 longer")
        attachments = store.requirements[uid]["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["size_bytes"] == 9

    def test_delete_attachment(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.add_attachment(uid, "z.pdf", b"z")
        ok = store.delete_attachment(uid, "z.pdf")
        assert ok is True
        assert not (store.attachment_dir(uid) / "z.pdf").exists()
        assert store.requirements[uid]["attachments"] == []

    def test_delete_nonexistent_returns_false(self, store):
        r = _make_req(store)
        ok = store.delete_attachment(r["uid"], "ghost.pdf")
        assert ok is False

    def test_list_attachments(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.add_attachment(uid, "a.pdf", b"a")
        store.add_attachment(uid, "b.pdf", b"b")
        lst = store.list_attachments(uid)
        assert len(lst) == 2
        names = {a["filename"] for a in lst}
        assert names == {"a.pdf", "b.pdf"}

    def test_attachment_works_for_principle(self, store):
        p = _make_principle(store)
        rec = store.add_attachment(p["uid"], "ref.pdf", b"ref")
        assert rec["filename"] == "ref.pdf"
        lst = store.list_attachments(p["uid"])
        assert len(lst) == 1

    def test_attachment_works_for_tbd(self, store):
        t = _make_tbd(store)
        store.add_attachment(t["uid"], "diagram.png", b"img")
        lst = store.list_attachments(t["uid"])
        assert len(lst) == 1


# ===========================================================================
# Comments
# ===========================================================================

class TestComments:
    def test_add_comment(self, store):
        r = _make_req(store)
        c = store.add_comment(r["uid"], "This needs work.", "alice")
        assert c["uid"]
        assert c["text"] == "This needs work."
        assert c["author"] == "alice"
        assert c["resolved"] is False

    def test_add_reply(self, store):
        r = _make_req(store)
        c1 = store.add_comment(r["uid"], "Parent", "alice")
        c2 = store.add_comment(r["uid"], "Reply", "bob", reply_to=c1["uid"])
        assert c2["reply_to"] == c1["uid"]

    def test_get_comments(self, store):
        r = _make_req(store)
        store.add_comment(r["uid"], "A", "alice")
        store.add_comment(r["uid"], "B", "bob")
        comments = store.get_comments(r["uid"])
        assert len(comments) == 2

    def test_update_comment(self, store):
        r = _make_req(store)
        c = store.add_comment(r["uid"], "Original", "alice")
        updated = store.update_comment(r["uid"], c["uid"], "Updated text")
        assert updated["text"] == "Updated text"
        assert updated["updated_at"] is not None

    def test_resolve_comment(self, store):
        r = _make_req(store)
        c = store.add_comment(r["uid"], "Resolve me", "alice")
        resolved = store.resolve_comment(r["uid"], c["uid"], True)
        assert resolved["resolved"] is True

    def test_reopen_comment(self, store):
        r = _make_req(store)
        c = store.add_comment(r["uid"], "X", "alice")
        store.resolve_comment(r["uid"], c["uid"], True)
        reopened = store.resolve_comment(r["uid"], c["uid"], False)
        assert reopened["resolved"] is False

    def test_delete_comment(self, store):
        r = _make_req(store)
        c = store.add_comment(r["uid"], "Delete me", "alice")
        ok = store.delete_comment(r["uid"], c["uid"])
        assert ok is True
        assert store.get_comments(r["uid"]) == []

    def test_delete_parent_leaves_reply(self, store):
        r = _make_req(store)
        c1 = store.add_comment(r["uid"], "Parent", "alice")
        c2 = store.add_comment(r["uid"], "Reply", "bob", reply_to=c1["uid"])
        store.delete_comment(r["uid"], c1["uid"])
        remaining = store.get_comments(r["uid"])
        assert len(remaining) == 1
        assert remaining[0]["uid"] == c2["uid"]

    def test_delete_nonexistent_returns_false(self, store):
        r = _make_req(store)
        assert store.delete_comment(r["uid"], "ghost-uid") is False

    def test_comments_stored_separately(self, store):
        r = _make_req(store)
        store.add_comment(r["uid"], "A", "alice")
        comments_file = store.comments_path(r["uid"])
        assert comments_file.exists()

    def test_comments_do_not_bump_req_version(self, store):
        r = _make_req(store)
        uid = r["uid"]
        v0 = r["version"]
        store.add_comment(uid, "A comment", "alice")
        assert store.requirements[uid]["version"] == v0

    def test_comments_work_for_principle(self, store):
        p = _make_principle(store)
        c = store.add_comment(p["uid"], "Principle note", "carol")
        assert c["author"] == "carol"
        assert len(store.get_comments(p["uid"])) == 1

    def test_comments_work_for_tbd(self, store):
        t = _make_tbd(store)
        store.add_comment(t["uid"], "TBD comment", "dave")
        assert len(store.get_comments(t["uid"])) == 1


# ===========================================================================
# Custom fields
# ===========================================================================

class TestCustomFields:
    def test_schema_save_load(self, store):
        schema = [{"key": "sprint", "label": "Sprint", "type": "string",
                   "required": False, "description": "", "options": [],
                   "default": None, "applies_to": ["requirement"]}]
        store.save_custom_field_schema(schema)
        loaded = store.load_custom_field_schema()
        assert len(loaded) == 1
        assert loaded[0]["key"] == "sprint"

    def test_empty_schema_no_errors(self, store):
        r = _make_req(store)
        errors = store.validate_custom_fields(r)
        assert errors == []

    def test_required_field_missing_produces_error(self, store):
        store.save_custom_field_schema([
            {"key": "cost", "label": "Cost", "type": "number",
             "required": True, "description": "", "options": [],
             "default": None, "applies_to": ["requirement"]}
        ])
        r = _make_req(store)
        errors = store.validate_custom_fields(r)
        assert len(errors) == 1
        assert "cost" in errors[0]["message"]

    def test_required_field_present_no_error(self, store):
        store.save_custom_field_schema([
            {"key": "cost", "label": "Cost", "type": "number",
             "required": True, "description": "", "options": [],
             "default": None, "applies_to": ["requirement"]}
        ])
        r = _make_req(store, custom_fields={"cost": 500})
        errors = store.validate_custom_fields(r)
        assert errors == []

    def test_invalid_number_produces_error(self, store):
        store.save_custom_field_schema([
            {"key": "cost", "label": "Cost", "type": "number",
             "required": False, "description": "", "options": [],
             "default": None, "applies_to": ["requirement"]}
        ])
        r = _make_req(store, custom_fields={"cost": "not-a-number"})
        errors = store.validate_custom_fields(r)
        assert any("cost" in e["message"] for e in errors)

    def test_select_invalid_option_produces_error(self, store):
        store.save_custom_field_schema([
            {"key": "tier", "label": "Tier", "type": "select",
             "required": False, "description": "",
             "options": ["gold", "silver", "bronze"],
             "default": None, "applies_to": ["requirement"]}
        ])
        r = _make_req(store, custom_fields={"tier": "platinum"})
        errors = store.validate_custom_fields(r)
        assert any("tier" in e["message"] for e in errors)

    def test_select_valid_option_no_error(self, store):
        store.save_custom_field_schema([
            {"key": "tier", "label": "Tier", "type": "select",
             "required": False, "description": "",
             "options": ["gold", "silver", "bronze"],
             "default": None, "applies_to": ["requirement"]}
        ])
        r = _make_req(store, custom_fields={"tier": "gold"})
        errors = store.validate_custom_fields(r)
        assert errors == []


# ===========================================================================
# Incremental reload
# ===========================================================================

class TestIncrementalReload:
    def test_reload_updated_file(self, store):
        r = _make_req(store)
        uid = r["uid"]
        # Simulate external edit
        data = load_yaml(store.req_path(uid))
        data["title"] = "Externally updated"
        data["last_modified"] = "2099-01-01T00:00:00Z"
        save_yaml(store.req_path(uid), data)
        store.reload_file(store.req_path(uid))
        assert store.requirements[uid]["title"] == "Externally updated"

    def test_reload_deleted_file(self, store):
        r = _make_req(store)
        uid = r["uid"]
        store.req_path(uid).unlink()
        store.reload_file(store.req_path(uid))
        assert uid not in store.requirements

    def test_config_change_triggers_full_reload(self, store):
        r = _make_req(store)
        store.reload_file(store.root / ".reqtool" / "config.yaml")
        # Requirement should still be present after full reload
        assert r["uid"] in store.requirements

    def test_skip_when_in_memory_is_current(self, store):
        r = _make_req(store)
        uid = r["uid"]
        # Tag the in-memory dict with a sentinel
        store.requirements[uid]["_sentinel"] = True
        # Reload with same last_modified -- should skip
        store.reload_file(store.req_path(uid))
        # Sentinel should still be there if reload was skipped
        # (disk version won't have the sentinel)
        assert store.requirements[uid].get("_sentinel") is True

    def test_transient_fnf_does_not_raise(self, store, tmp_path):
        # Reload a path that doesn't exist -- should not raise
        ghost = store.root / "requirements" / "ghost.yaml"
        store.reload_file(ghost)  # should not raise


# ===========================================================================
# Search
# ===========================================================================

class TestSearch:
    def test_search_by_title(self, store):
        _make_req(store, id="REQ-001", title="Temperature sensor accuracy")
        _make_req(store, id="REQ-002", title="Battery life requirement")
        results = store.search_uids("temperature", limit=10)
        ids = [r["id"] for r in results]
        assert "REQ-001" in ids
        assert "REQ-002" not in ids

    def test_search_case_insensitive(self, store):
        _make_req(store, id="REQ-001", title="The FIRMWARE watchdog shall fire")
        results = store.search_uids("firmware", limit=10)
        assert any(r["id"] == "REQ-001" for r in results)

    def test_search_across_types(self, store):
        _make_req(store, title="Security requirement")
        _make_principle(store, title="Security principle")
        results = store.search_uids("security", limit=20)
        types = {r["type"] for r in results}
        assert "requirement" in types
        assert "principle" in types

    def test_search_empty_query_returns_results(self, store):
        _make_req(store)
        results = store.search_uids("", limit=10)
        assert isinstance(results, list)


# ===========================================================================
# Tree building
# ===========================================================================

class TestBuildTree:
    def test_flat_tree(self, store):
        r = _make_req(store)
        tree = store.build_tree()
        assert any(n["uid"] == r["uid"] for n in tree)

    def test_parent_child_tree(self, store):
        parent = _make_req(store, id="P")
        child = store.create_requirement({
            "id": "C", "title": "Child",
            "parentId": parent["uid"],
            "content": {"description": "", "rationale": "", "extended_description": ""},
        })
        tree = store.build_tree()
        parent_node = next(n for n in tree if n["uid"] == parent["uid"])
        child_uids = [c["uid"] for c in parent_node.get("children", [])]
        assert child["uid"] in child_uids

    def test_deleted_not_in_tree(self, store):
        r = _make_req(store)
        store.delete_requirement(r["uid"])
        tree = store.build_tree()
        uids = [n["uid"] for n in tree]
        assert r["uid"] not in uids
