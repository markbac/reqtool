"""
tests/test_atam_and_demo_repo.py
================================
Tests for ATAM Decision Record evaluation and demo repository creation script.
"""

from pathlib import Path
import pytest
from reqtool.store import Store
from reqtool.exports import export_adr_markdown
from scripts.create_demo_repo import build_demo_repository


def test_atam_decision_record(tmp_path: Path):
    for d in ("requirements", "principles", "decisions", "tbds", ".reqtool"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    store = Store(tmp_path)
    store.load()

    store.create_decision({
        "type": "decision",
        "id": "DEC-ATAM-001",
        "title": "Protocol Selection ATAM Evaluation",
        "status": "accepted",
        "owner": "Systems Architect",
        "content": {
            "context": "Evaluating IoT wireless connectivity.",
            "options": [
                {"name": "Matter over Thread", "pros": ["Low sleep power"], "cons": ["Border router required"]},
            ],
            "chosen_option": "Matter over Thread",
            "rationale": "Enables 2-year battery life.",
            "atam": {
                "enabled": True,
                "quality_attributes": ["battery_life", "latency"],
                "sensitivity_points": [
                    {"attribute": "battery_life", "description": "Radio sleep current sensitivity."},
                ],
                "tradeoff_points": [
                    {"attributes": ["battery_life", "latency"], "description": "Thread polling interval trade-off."},
                ],
                "risks": ["Border router dependency"],
                "non_risks": ["Hardware AES acceleration"],
            },
        },
    })

    md_export = export_adr_markdown(store)
    assert "### ATAM Architecture Tradeoff Analysis" in md_export
    assert "battery_life, latency" in md_export
    assert "Radio sleep current sensitivity." in md_export
    assert "Thread polling interval trade-off." in md_export
    assert "⚠️ Border router dependency" in md_export
    assert "✅ Hardware AES acceleration" in md_export


def test_build_demo_repository(tmp_path: Path):
    demo_dir = tmp_path / "demo_repo"
    build_demo_repository(demo_dir)

    store = Store(demo_dir)
    store.load()

    assert len(store.requirements) > 200
    assert len(store.principles) >= 10
    assert len(store.decisions) >= 5
    dec_ids = [d.get("id") for d in store.decisions.values()]
    assert "DEC-001" in dec_ids
    assert "DEC-002" in dec_ids
