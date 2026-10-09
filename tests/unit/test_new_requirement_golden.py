"""ARC-06: a new requirement is built from the typed model and must look exactly as it did when it was a dict literal."""

import json
from pathlib import Path

import pytest

from reqtool.store import Store

GOLDEN = json.loads((Path(__file__).resolve().parents[1] / "golden" / "new_requirement.json").read_text(encoding="utf-8"))
CASES = {
    "minimal": {"title": "Minimal"},
    "full": {"title": "Full", "req_type": "story", "priority": "high", "owner": "alice", "tags": ["a", "b"],
             "allocated_to": ["t"], "content": {"description": "d", "rationale": "r", "extended_description": ""},
             "estimate": 3, "estimate_unit": "points", "safety_related": True, "asil_level": "ASIL-B",
             "verification_method": "inspection", "custom_fields": {"k": 1}, "attachments": [{"name": "x"}],
             "nfr": {"latency_ms": 5}, "unknown_key": "dropped", "version": "9.9.9", "history": [1],
             "deleted": True, "status": "ready"},
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_new_requirement_matches_the_golden_file(repo_root, name):
    store = Store(repo_root)
    store.load()
    made = json.loads(json.dumps(store.create_requirement(dict(CASES[name]))))
    for key in ("uid", "created", "last_modified", "content_hash", "tool_version"):
        made[key] = "<x>"
    for entry in made["history"]:
        entry["date"] = "<x>"
    assert list(made) == GOLDEN[name]["keys"], "key order changed"
    assert made == GOLDEN[name]["data"]


def test_the_caller_cannot_set_system_fields(repo_root):
    store = Store(repo_root)
    store.load()
    made = store.create_requirement({"title": "t", "version": "9.9.9", "deleted": True, "history": [1], "uid": "x"})
    assert (made["version"], made["deleted"]) == ("1.0.0", False)
    assert [h["summary"] for h in made["history"]] == ["Initial draft."]  # the tool's entry, not the caller's
    assert made["uid"] != "x"
