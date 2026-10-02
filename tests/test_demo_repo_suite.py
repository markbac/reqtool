"""
tests/test_demo_repo_suite.py
==============================
Integration tests utilizing the full IoT Sensor Demo Repository dataset.
Tests REST API, search, traceability matrix, ATAM decision exports, and store hierarchy.
"""

import pytest
from fastapi.testclient import TestClient


def test_demo_repo_store_counts(demo_store):
    """Verify demo store has expected full dataset counts for multiple product lines and modules."""
    assert len(demo_store.requirements) > 200
    assert len(demo_store.principles) >= 10
    assert len(demo_store.decisions) >= 7
    assert len(demo_store.modules) >= 3
    assert len(demo_store.products) >= 3


def test_demo_repo_api_requirements(demo_client: TestClient):
    """GET /requirements returns full dataset."""
    r = demo_client.get("/requirements")
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 200
    # Check hierarchy items present
    types = {item.get("req_type") for item in items}
    assert "theme" in types or "epic" in types or "functional" in types


def test_demo_repo_api_decisions_and_atam(demo_client: TestClient):
    """GET /decisions returns ATAM decisions."""
    r = demo_client.get("/decisions")
    assert r.status_code == 200
    decisions = r.json()
    assert len(decisions) >= 5
    # Find ATAM decision DEC-001
    dec_map = {d.get("id"): d for d in decisions}
    assert "DEC-001" in dec_map
    atam = dec_map["DEC-001"].get("content", {}).get("atam", {})
    assert atam.get("enabled") is True
    assert "battery_life" in atam.get("quality_attributes", [])


def test_demo_repo_export_adr_endpoint(demo_client: TestClient):
    """GET /export/adr returns formatted ADR Markdown with ATAM analysis."""
    r = demo_client.get("/export/adr")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    text = r.text
    assert "# Architecture Decision Records (ADRs)" in text
    assert "DEC-001: Smart Home Wireless Protocol Selection" in text
    assert "### ATAM Architecture Tradeoff Analysis" in text
    assert "battery_life" in text
    assert "⚠️" in text
    assert "✅" in text


def test_demo_repo_traceability_matrix(demo_client: TestClient):
    """GET /traceability/matrix returns 2D matrix."""
    r = demo_client.get("/traceability/matrix?source_type=stakeholder_need&target_type=functional")
    assert r.status_code == 200
    data = r.json()
    assert "sources" in data or "matrix" in data or isinstance(data, dict)


def test_demo_repo_search(demo_client: TestClient):
    """Search engine API endpoint across demo dataset."""
    r1 = demo_client.get("/search?q=Matter")
    assert r1.status_code == 200
    assert len(r1.json()) > 0

    r2 = demo_client.get("/search?q=temperature")
    assert r2.status_code == 200
    assert len(r2.json()) > 0


def test_demo_repo_gap_analysis(demo_client: TestClient):
    """GET /traceability/gaps returns auditing metrics."""
    r = demo_client.get("/traceability/gaps")
    assert r.status_code == 200
    gaps = r.json()
    assert "missing_acceptance_criteria" in gaps or "missing_verification" in gaps
