"""
tests/test_pdf_export.py
=========================
Unit and integration tests for reqtool PDF exporter engine and API endpoints.
"""

from pathlib import Path
from reqtool.exports import export_pdf


def test_export_pdf_bytes_generation(demo_store):
    """Verify export_pdf produces valid PDF bytes starting with %PDF- header."""
    pdf_bytes = export_pdf(demo_store)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 50000  # Detailed PDF specification
    assert pdf_bytes.startswith(b"%PDF-")


def test_export_pdf_api_endpoint(demo_client):
    """Verify GET /export/pdf returns 200 OK and application/pdf content type."""
    resp = demo_client.get("/export/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")


def test_repo_config_description_update(demo_client):
    """Verify PUT /config updates repository title and overarching description."""
    body = {
        "repo_title": "Updated IoT Sensor Suite",
        "repo_description": "Overarching description for testing PDF header text.",
    }
    resp = demo_client.put("/config", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo_title"] == "Updated IoT Sensor Suite"
    assert data["repo_description"] == "Overarching description for testing PDF header text."

    # Verify GET /repo reflects the change
    repo_resp = demo_client.get("/repo")
    assert repo_resp.status_code == 200
    repo_data = repo_resp.json()
    assert repo_data["repo_title"] == "Updated IoT Sensor Suite"
    assert repo_data["repo_description"] == "Overarching description for testing PDF header text."
