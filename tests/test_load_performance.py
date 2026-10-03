"""PERF-05: loading many requirements is fast, and the safe loader reads values exactly as before."""
import subprocess
import time

from ruamel.yaml import YAML

from reqtool.fileio import _to_plain, load_yaml, save_yaml
from reqtool.store import Store

N = 2000
BUDGET_SECONDS = 15.0  # measured 1.1 s with libyaml and about 3 s without; the old loader needed about 16 s

TEMPLATE = """uid: {uid}
id: FR-{i:04d}
title: Requirement {i}
status: draft
priority: medium
req_type: functional
content:
  description: The system shall do thing {i} within 5 seconds.
  rationale: Because reasons.
tags:
- a
- b
acceptance_criteria:
- id: AC-1
  text: Given a when b then c
version: 1
"""


def test_load_2000_requirements_within_budget(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".reqtool").mkdir()
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    for i in range(N):
        uid = f"01a10265-d9b6-75ed-85df-{i:012x}"
        (reqs / f"{uid}.yaml").write_text(TEMPLATE.format(uid=uid, i=i), encoding="utf-8")
    store = Store(tmp_path)
    start = time.perf_counter()
    store.load()
    elapsed = time.perf_counter() - start
    assert len(store.requirements) == N
    assert elapsed < BUDGET_SECONDS, f"loading {N} requirements took {elapsed:.1f}s"


def test_safe_loader_matches_round_trip_loader(tmp_path):
    text = (
        "status: yes\nflag: true\nversion: '1.10'\ncount: 007\nplain: 1.10\nwhen: 2026-01-01\n"
        "at: 2026-01-01T10:00:00Z\nclock: 12:30:00\nnothing: ~\nnested:\n  - a: 1\n    b: [x, y]\n"
    )
    p = tmp_path / "x.yaml"
    p.write_text(text, encoding="utf-8")
    assert load_yaml(p) == _to_plain(YAML().load(text))
    assert load_yaml(p)["status"] == "yes"  # YAML 1.2: not a boolean


def test_save_then_load_round_trips(tmp_path):
    data = {"uid": "u", "title": "T", "status": "yes", "n": 3, "tags": ["a"], "c": {"d": "e: f"}}
    p = tmp_path / "y.yaml"
    save_yaml(p, data)
    assert load_yaml(p) == data
