"""QA-04: every API operation is classified in ui-coverage.yaml, and the classification matches the UI source."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_ui_coverage as cov  # noqa: E402


def test_every_operation_is_classified_and_classifications_are_current():
    assert cov.problems() == []


def test_an_unclassified_operation_is_reported(monkeypatch):
    real = cov.load_coverage()
    trimmed = {k: v for k, v in real.items() if k != "GET /requirements"}
    monkeypatch.setattr(cov, "load_coverage", lambda: trimmed)
    assert "unclassified operation: GET /requirements" in cov.problems()


def test_a_stale_entry_is_reported(monkeypatch):
    real = dict(cov.load_coverage())
    real["GET /no/such/route"] = {"status": "backend-only", "reason": "x"}
    monkeypatch.setattr(cov, "load_coverage", lambda: real)
    assert any("does not exist" in p for p in cov.problems())
