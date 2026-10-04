"""QA-05: the published copies of shared documents must match the canonical root copy."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_shared_documents_are_in_sync():
    spec = importlib.util.spec_from_file_location("sync_docs", ROOT / "scripts" / "sync_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.out_of_sync() == []
