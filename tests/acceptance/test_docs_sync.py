"""QA-05: the published copies of shared documents must match the canonical root copy."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_shared_documents_are_in_sync():
    spec = importlib.util.spec_from_file_location("sync_docs", ROOT / "scripts" / "sync_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.out_of_sync() == []


def test_openapi_yaml_matches_the_app(tmp_path):
    """openapi.yaml is generated: run ``req openapi`` after changing an endpoint."""
    import yaml
    from reqtool.api import create_app
    for d in ("requirements", "principles", "decisions", ".reqtool"):
        (tmp_path / d).mkdir()
    committed = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    assert committed == create_app(tmp_path).openapi(), "openapi.yaml is stale: run `req openapi`"
