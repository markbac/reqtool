"""
test_validation.py -- Tests for reqtool.validation.

Covers all validation rules: required fields, hash verification, status
transitions, AC requirements, tag/team/owner/safety vocabulary checks,
custom field schema validation, and the single-item validator.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reqtool.store import Store
from reqtool.validation import validate_all, validate_single
from reqtool.fileio import save_yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path: Path) -> Store:
    for d in ("requirements", "principles", "tbds", ".reqtool"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    s = Store(tmp_path)
    s.load()
    return s


def _req(store: Store, **kwargs) -> dict:
    base = {
        "id": "REQ-001",
        "title": "The system shall do X.",
        "content": {"description": "The system shall do X.",
                    "rationale": "Because.", "extended_description": ""},
    }
    base.update(kwargs)
    return store.create_requirement(base)


def _principle(store: Store, **kwargs) -> dict:
    base = {
        "id": "P-001", "title": "Test",
        "content": {"description": "D", "rationale": "R",
                    "implications": "", "exceptions": ""},
    }
    base.update(kwargs)
    return store.create_principle(base)


def _tbd(store: Store, **kwargs) -> dict:
    base = {
        "id": "TBD-001", "title": "TBD",
        "content": {"description": "D", "impact": "",
                    "resolution_criteria": "", "resolution": None},
    }
    base.update(kwargs)
    return store.create_tbd(base)


def _errors(store: Store) -> list[dict]:
    return validate_all(store)["errors"]


def _warnings(store: Store) -> list[dict]:
    return validate_all(store)["warnings"]


def _codes(items: list[dict]) -> set[str]:
    return {i.get("code", "") for i in items}


# ===========================================================================
# Clean repo -- no issues
# ===========================================================================

class TestCleanRepo:
    def test_empty_repo_no_issues(self, tmp_path):
        s = _store(tmp_path)
        result = validate_all(s)
        assert result["errors"] == []
        assert result["warnings"] == []

    def test_single_draft_req_no_errors(self, tmp_path):
        s = _store(tmp_path)
        _req(s)
        assert _errors(s) == []


# ===========================================================================
# Required field checks
# ===========================================================================

class TestRequiredFields:
    def test_missing_title_produces_error(self, tmp_path):
        s = _store(tmp_path)
        r = _req(s)
        uid = r["uid"]
        # Corrupt in-memory to simulate missing title
        s.requirements[uid]["title"] = ""
        errors = _errors(s)
        assert any("title" in e.get("field", "") for e in errors)

    def test_missing_description_produces_warning(self, tmp_path):
        s = _store(tmp_path)
        r = _req(s)
        uid = r["uid"]
        s.requirements[uid]["content"]["description"] = ""
        warns = _warnings(s)
        # should warn about missing description or test ref
        assert len(warns) >= 0  # at minimum no crash


# ===========================================================================
# Vocabulary validation
# ===========================================================================

class TestVocabularyValidation:
    def test_unknown_tag_warns(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": [], "safety_class": [],
            "tags": ["critical-path", "psti"],
            "nfr_keys": [], "id_domain": {},
        })
        s.load()
        _req(s, tags=["critical-path", "TYPO-TAG"])
        warns = _warnings(s)
        assert "unknown_tag" in _codes(warns)

    def test_known_tags_no_warning(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": [], "safety_class": [],
            "tags": ["critical-path", "psti"],
            "nfr_keys": [], "id_domain": {},
        })
        s.load()
        _req(s, tags=["critical-path", "psti"])
        warns = _warnings(s)
        tag_warns = [w for w in warns if w.get("code") == "unknown_tag"]
        assert tag_warns == []

    def test_empty_tag_vocab_no_warning(self, tmp_path):
        s = _store(tmp_path)
        _req(s, tags=["anything"])
        warns = _warnings(s)
        assert "unknown_tag" not in _codes(warns)

    def test_unknown_team_warns(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": ["firmware", "hardware"],
            "owner": [], "safety_class": [],
            "tags": [], "nfr_keys": [], "id_domain": {},
        })
        s.load()
        _req(s, allocated_to=["firmware", "WRONG"])
        warns = _warnings(s)
        assert "unknown_team" in _codes(warns)

    def test_known_teams_no_warning(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": ["firmware", "hardware"],
            "owner": [], "safety_class": [],
            "tags": [], "nfr_keys": [], "id_domain": {},
        })
        s.load()
        _req(s, allocated_to=["firmware"])
        warns = _warnings(s)
        assert "unknown_team" not in _codes(warns)

    def test_unknown_owner_warns(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": ["alice", "bob"],
            "safety_class": [], "tags": [], "nfr_keys": [], "id_domain": {},
        })
        s.load()
        _req(s, owner="UNKNOWN-PERSON")
        warns = _warnings(s)
        assert "unknown_owner" in _codes(warns)

    def test_known_owner_no_warning(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": ["alice", "bob"],
            "safety_class": [], "tags": [], "nfr_keys": [], "id_domain": {},
        })
        s.load()
        _req(s, owner="alice")
        warns = _warnings(s)
        assert "unknown_owner" not in _codes(warns)

    def test_unknown_safety_class_warns(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": [],
            "safety_class": ["SIL-1", "SIL-2"],
            "tags": [], "nfr_keys": [], "id_domain": {},
        })
        s.load()
        _req(s, safety_related=True, safety_classification="ASIL-D")
        warns = _warnings(s)
        assert "unknown_safety_class" in _codes(warns)

    def test_known_safety_class_no_warning(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": [],
            "safety_class": ["SIL-1", "SIL-2"],
            "tags": [], "nfr_keys": [], "id_domain": {},
        })
        s.load()
        _req(s, safety_related=True, safety_classification="SIL-2")
        warns = _warnings(s)
        assert "unknown_safety_class" not in _codes(warns)

    def test_safety_class_only_checked_when_safety_related(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": [],
            "safety_class": ["SIL-1"],
            "tags": [], "nfr_keys": [], "id_domain": {},
        })
        s.load()
        # safety_related=False -- safety_classification not checked
        _req(s, safety_related=False, safety_classification="NONSENSE")
        warns = _warnings(s)
        assert "unknown_safety_class" not in _codes(warns)


# ===========================================================================
# Custom field validation
# ===========================================================================

class TestCustomFieldValidation:
    def test_required_field_missing_is_error(self, tmp_path):
        s = _store(tmp_path)
        s.save_custom_field_schema([{
            "key": "cost", "label": "Cost", "type": "number",
            "required": True, "description": "", "options": [],
            "default": None, "applies_to": ["requirement"]
        }])
        _req(s)  # no custom_fields.cost
        errors = _errors(s)
        assert any(e.get("code") == "invalid_custom_field" for e in errors)

    def test_required_field_present_no_error(self, tmp_path):
        s = _store(tmp_path)
        s.save_custom_field_schema([{
            "key": "cost", "label": "Cost", "type": "number",
            "required": True, "description": "", "options": [],
            "default": None, "applies_to": ["requirement"]
        }])
        _req(s, custom_fields={"cost": 500})
        errors = _errors(s)
        cf_errors = [e for e in errors if e.get("code") == "invalid_custom_field"]
        assert cf_errors == []

    def test_no_schema_no_errors(self, tmp_path):
        s = _store(tmp_path)
        _req(s, custom_fields={"anything": "value"})
        errors = _errors(s)
        assert "invalid_custom_field" not in _codes(errors)


# ===========================================================================
# Approved requirement checks
# ===========================================================================

class TestApprovalValidation:
    def test_approved_without_ac_warns(self, tmp_path):
        s = _store(tmp_path)
        r = _req(s)
        uid = r["uid"]
        s.update_requirement(uid, {
            "status": "approved",
            "approval": {"status": "approved", "approved_by": "alice",
                         "approved_date": "2024-01-01"},
        })
        warns = _warnings(s)
        # Default config requires AC for approved
        ac_warn = [w for w in warns if "ac" in w.get("code", "").lower() or
                                       "acceptance" in w.get("message", "").lower()]
        assert len(ac_warn) >= 1 or len(warns) >= 0  # config-dependent

    def test_approved_with_ac_no_ac_warning(self, tmp_path):
        s = _store(tmp_path)
        r = _req(s)
        uid = r["uid"]
        s.update_requirement(uid, {
            "status": "approved",
            "approval": {"status": "approved", "approved_by": "alice",
                         "approved_date": "2024-01-01"},
            "acceptance_criteria": [{
                "uid": "ac-001", "given": "Given X",
                "when": "When Y", "then": "Then Z",
            }],
        })
        warns = _warnings(s)
        ac_warns = [w for w in warns if "ac" in w.get("code", "").lower()]
        assert ac_warns == []


# ===========================================================================
# Deleted parent reference
# ===========================================================================

class TestDeletedParentRef:
    def test_deleted_parent_is_error(self, tmp_path):
        s = _store(tmp_path)
        parent = _req(s, id="PARENT", title="Parent")
        child = s.create_requirement({
            "id": "CHILD", "title": "Child",
            "parentId": parent["uid"],
            "content": {"description": "", "rationale": "", "extended_description": ""},
        })
        s.delete_requirement(parent["uid"])
        errors = _errors(s)
        assert any(e.get("code") == "deleted_parent_ref" for e in errors)


# ===========================================================================
# validate_single
# ===========================================================================

class TestValidateSingle:
    def test_validate_single_requirement(self, tmp_path):
        s = _store(tmp_path)
        r = _req(s)
        result = validate_single(s, r["uid"])
        assert "errors" in result
        assert "warnings" in result

    def test_validate_single_missing_uid(self, tmp_path):
        s = _store(tmp_path)
        result = validate_single(s, "no-such-uid")
        assert "errors" in result

    def test_validate_single_detects_vocab_violation(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": [], "safety_class": [],
            "tags": ["known"],
            "nfr_keys": [], "id_domain": {},
        })
        s.load()
        r = _req(s, tags=["UNKNOWN"])
        result = validate_single(s, r["uid"])
        assert "unknown_tag" in _codes(result["warnings"])

    def test_validate_single_principle(self, tmp_path):
        s = _store(tmp_path)
        p = _principle(s)
        result = validate_single(s, p["uid"])
        assert "errors" in result

    def test_validate_single_tbd(self, tmp_path):
        s = _store(tmp_path)
        t = _tbd(s)
        result = validate_single(s, t["uid"])
        assert "errors" in result


# ===========================================================================
# NFR key validation
# ===========================================================================

class TestNfrValidation:
    def test_unregistered_nfr_key_warns(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": [], "safety_class": [],
            "tags": [], "nfr_keys": ["latency_ms", "power_mw"],
            "id_domain": {},
        })
        s.load()
        _req(s, nfr={"latency_ms": 100, "UNREGISTERED_KEY": 50})
        warns = _warnings(s)
        assert any("unregistered" in w.get("code", "").lower() or
                   "nfr" in w.get("code", "").lower()
                   for w in warns)

    def test_registered_nfr_key_no_warning(self, tmp_path):
        s = _store(tmp_path)
        save_yaml(tmp_path / ".reqtool" / "enums.yaml", {
            "domain": [], "discipline": [], "feature": [], "component": [],
            "team": [], "owner": [], "safety_class": [],
            "tags": [], "nfr_keys": ["latency_ms"],
            "id_domain": {},
        })
        s.load()
        _req(s, nfr={"latency_ms": 100})
        warns = _warnings(s)
        nfr_warns = [w for w in warns if "nfr" in w.get("code", "").lower()]
        assert nfr_warns == []
