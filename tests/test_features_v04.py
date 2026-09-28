"""
tests/test_features_v04.py
==========================
Unit and integration tests for Product Principles, Module Variable Substitution,
Product Module Overlays, and Remote Git Module Imports.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from reqtool.store import Store
from reqtool.api import create_app
from reqtool.validation import validate_all
from reqtool.fileio import save_yaml, uuid7, utcnow_iso


def find_node(nodes: list[dict], uid: str) -> dict | None:
    for n in nodes:
        if n.get("uid") == uid:
            return n
        if n.get("children"):
            res = find_node(n["children"], uid)
            if res:
                return res
    return None


class TestProductPrinciplesAndNFR:
    def test_unmapped_product_principle_warns(self, tmp_path: Path):
        store = Store(tmp_path)
        p_uid = uuid7()
        now = utcnow_iso()
        principle = {
            "schema_version": "1.0.0",
            "type": "principle",
            "tool_version": "0.3.20",
            "uid": p_uid,
            "id": "PRIN-PRODUCT-01",
            "title": "Low Latency NFR",
            "version": "1.0.0",
            "status": "approved",
            "principle_kind": "product_nfr",
            "nfr_targets": {"latency": "100ms"},
            "content": {"description": "Product must respond in under 100ms"},
            "created": now,
            "last_modified": now,
            "history": [],
        }
        store.principles[p_uid] = principle

        res = validate_all(store)
        warnings = [w for w in res["warnings"] if w["code"] == "unmapped_product_principle"]
        assert len(warnings) == 1
        assert warnings[0]["uid"] == p_uid

    def test_satisfied_product_principle_no_warning(self, tmp_path: Path):
        store = Store(tmp_path)
        p_uid = uuid7()
        req_uid = uuid7()
        now = utcnow_iso()

        store.principles[p_uid] = {
            "schema_version": "1.0.0", "type": "principle", "tool_version": "0.3.20",
            "uid": p_uid, "id": "PRIN-NFR-02", "title": "High Availability",
            "version": "1.0.0", "status": "approved", "principle_kind": "product_nfr",
            "nfr_targets": {"reliability": "99.99%"},
            "content": {"description": "High availability NFR"},
            "created": now, "last_modified": now, "history": [],
        }
        store.requirements[req_uid] = {
            "schema_version": "1.0.0", "type": "requirement", "tool_version": "0.3.20",
            "uid": req_uid, "id": "REQ-HA-01", "title": "Redundant Servers",
            "status": "approved", "priority": "high", "req_type": "functional",
            "version": "1.0.0",
            "content": {"description": "Deploy across multiple zones"},
            "relationships": [{"type": "satisfies", "target": {"uid": p_uid}}],
            "created": now, "last_modified": now, "history": [],
        }

        res = validate_all(store)
        warnings = [w for w in res["warnings"] if w["code"] == "unmapped_product_principle"]
        assert len(warnings) == 0


class TestModuleTemplateVariablesAndOverlays:
    def test_variable_substitution_in_build_tree(self, tmp_path: Path):
        store = Store(tmp_path)
        p_uid = uuid7()
        mod_req_uid = uuid7()
        now = utcnow_iso()

        store.products["prod-a"] = {
            "schema_version": "1.0.0", "type": "product", "tool_version": "0.3.20",
            "uid": p_uid, "id": "prod-a", "title": "Product A", "version": "1.0.0",
            "variables": {"max_speed": "250 km/h", "brand": "HyperSpeed"},
            "modules": [{"id": "engine-mod"}],
            "created": now, "last_modified": now, "history": [],
        }
        store.modules["engine-mod"] = {"id": "engine-mod", "title": "Engine Module", "overrideable": ["title"]}
        store.module_requirements["engine-mod"] = {
            mod_req_uid: {
                "schema_version": "1.0.0", "type": "requirement", "tool_version": "0.3.20",
                "uid": mod_req_uid, "id": "MOD-ENG-01",
                "title": "Top speed shall reach {{max_speed}} for {{brand}}",
                "status": "approved", "priority": "high", "req_type": "functional",
                "content": {"description": "Vehicle speed specification for {{brand}}"},
                "version": "1.0.0", "created": now, "last_modified": now, "history": [],
            }
        }

        tree = store.build_tree(product_id="prod-a")
        mod_node = find_node(tree, mod_req_uid)
        assert mod_node is not None
        assert mod_node["title"] == "Top speed shall reach 250 km/h for HyperSpeed"

    def test_product_module_overlay(self, tmp_path: Path):
        store = Store(tmp_path)
        p_uid = uuid7()
        mod_req_uid = uuid7()
        now = utcnow_iso()

        store.products["prod-b"] = {
            "schema_version": "1.0.0", "type": "product", "tool_version": "0.3.20",
            "uid": p_uid, "id": "prod-b", "title": "Product B", "version": "1.0.0",
            "modules": [{
                "id": "safety-mod",
                "overlay": {
                    mod_req_uid: {"title": "Overridden Safety Title", "priority": "critical"},
                }
            }],
            "created": now, "last_modified": now, "history": [],
        }
        store.modules["safety-mod"] = {"id": "safety-mod", "title": "Safety Module"}
        store.module_requirements["safety-mod"] = {
            mod_req_uid: {
                "schema_version": "1.0.0", "type": "requirement", "tool_version": "0.3.20",
                "uid": mod_req_uid, "id": "MOD-SAF-01",
                "title": "Original Safety Title",
                "status": "draft", "priority": "medium", "req_type": "safety",
                "version": "1.0.0", "created": now, "last_modified": now, "history": [],
            }
        }

        tree = store.build_tree(product_id="prod-b")
        node = find_node(tree, mod_req_uid)
        assert node is not None
        assert node["title"] == "Overridden Safety Title"
        assert node["priority"] == "critical"


class TestRemoteGitModuleFetch:
    def test_fetch_remote_module_requires_manifest(self, tmp_path: Path):
        store = Store(tmp_path)
        with pytest.raises(ValueError, match="Module manifest for 'nonexistent-mod' not found"):
            store.fetch_remote_module("nonexistent-mod")
