"""
tests/test_decisions_adr.py
===========================
Tests for Decision Records (ADR), status lifecycle, supersedes lineage, and ADR Exporter.
"""

from pathlib import Path
from reqtool.store import Store
from reqtool.exports import export_adr_markdown


def test_create_decision_record(tmp_path: Path):
    for d in ("requirements", "principles", "decisions", "tbds", ".reqtool"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    store = Store(tmp_path)
    store.load()

    d1 = store.create_decision({
        "type": "decision",
        "title": "Use REST API with OpenAPI 3.1",
        "status": "proposed",
        "owner": "Architecture Group",
        "content": {
            "context": "We need a standard protocol for API communication.",
            "options": [
                {
                    "name": "Option A: REST / OpenAPI 3.1",
                    "pros": ["Standard tooling", "Human-readable"],
                    "cons": ["Payload size"],
                },
                {
                    "name": "Option B: gRPC / Protobuf",
                    "pros": ["Performance"],
                    "cons": ["Complex frontend proxy"],
                },
            ],
            "chosen_option": "Option A: REST / OpenAPI 3.1",
            "rationale": "Aligns with EG-004 and existing FastAPI framework.",
        }
    })

    assert d1["uid"] is not None
    assert d1["id"].startswith("DEC-")
    assert d1["status"] == "proposed"
    assert len(d1["content"]["options"]) == 2
    assert store.get_decision(d1["uid"]) is not None


def test_decision_lineage_supersedes(tmp_path: Path):
    for d in ("requirements", "principles", "decisions", "tbds", ".reqtool"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    store = Store(tmp_path)
    store.load()

    # Initial decision DEC-1
    dec1 = store.create_decision({
        "type": "decision",
        "id": "DEC-001",
        "title": "Initial Database Choice",
        "status": "accepted",
    })
    assert dec1["status"] == "accepted"

    # New decision DEC-2 that supersedes DEC-1
    dec2 = store.create_decision({
        "type": "decision",
        "id": "DEC-002",
        "title": "Migrate Database to Postgres",
        "status": "accepted",
        "supersedes": dec1["uid"],
    })

    # Reload store
    store.load()
    reloaded_dec1 = store.get_decision(dec1["uid"])
    reloaded_dec2 = store.get_decision(dec2["uid"])

    assert reloaded_dec1["status"] == "superseded"
    assert reloaded_dec1["superseded_by"] == dec2["uid"]
    assert reloaded_dec2["supersedes"] == dec1["uid"]


def test_export_adr_markdown(tmp_path: Path):
    for d in ("requirements", "principles", "decisions", "tbds", ".reqtool"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    store = Store(tmp_path)
    store.load()

    store.create_decision({
        "type": "decision",
        "id": "DEC-001",
        "title": "Adopt Architecture Decision Records",
        "status": "accepted",
        "owner": "Systems Engineering",
        "content": {
            "context": "We need formal governance over technical choices.",
            "options": [
                {"name": "Option A: Decision Records", "pros": ["Structured", "Nygard standard"]},
            ],
            "chosen_option": "Option A: Decision Records",
            "rationale": "Directly matches EG-008 in Engineering Process.",
        }
    })

    md_output = export_adr_markdown(store)
    assert "# Architecture Decision Records (ADRs)" in md_output
    assert "DEC-001: Adopt Architecture Decision Records" in md_output
    assert "* **Status**: `Accepted`" in md_output
    assert "Option A: Decision Records" in md_output
