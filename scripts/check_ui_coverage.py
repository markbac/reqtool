#!/usr/bin/env python3
"""Check that every API operation is classified in ``ui-coverage.yaml`` (QA-04).

Each OpenAPI operation must be listed with one of:

``surfaced``      the UI calls it
``partial``       the UI uses it in part (say how in ``note``)
``backend-only``  not meant for the UI (give the ``reason``)
``planned``       the UI should call it and does not yet (give the ``ref`` issue)

The check fails when an operation is unclassified, when an entry names an operation that no longer
exists, when a ``surfaced``/``partial`` operation is not called anywhere in the UI source, and when
a ``backend-only``/``planned`` one is (the entry is stale).

    python scripts/check_ui_coverage.py            # check
    python scripts/check_ui_coverage.py --update   # add missing operations as 'unclassified'
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
UI_SRC = ROOT / "src" / "reqtool" / "ui" / "src"
COVERAGE = ROOT / "ui-coverage.yaml"
STATUSES = {"surfaced", "partial", "backend-only", "planned"}

_HELPER_CALL = re.compile(r"""\b(get|post|put|del)\(\s*(?P<q>[`'"])(?P<path>/(?:\$\{[^}]*\}|[^`'"$])*)(?P=q)""")
_FETCH_CALL = re.compile(r"""fetch\(\s*`\$\{getBaseUrl\(\)\}(?P<path>/[^`]*)`(?P<opts>.{0,300})""", re.S)
_METHOD = {"get": "GET", "post": "POST", "put": "PUT", "del": "DELETE"}


def _normalise(path: str) -> str:
    path = re.sub(r"\$\{[^}]*\?[^}]*\}", "", path)  # ${cond ? '?query' : ''} is an optional query string
    path = path.split("?", 1)[0]
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    path = re.sub(r"\{[^}/]*\}", "{}", path)
    return path.rstrip("/") or "/"


def operations() -> dict[str, str]:
    """``{"GET /requirements/{uid}": "/requirements/{}"}`` for every operation the API declares."""
    sys.path.insert(0, str(ROOT / "src"))
    from reqtool.api import create_app
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for d in ("requirements", "principles", "decisions", ".reqtool"):
            (root / d).mkdir()
        schema = create_app(root).openapi()
    ops = {}
    for path, item in schema["paths"].items():
        for method in item:
            if method.upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                ops[f"{method.upper()} {path}"] = _normalise(path)
    return ops


def ui_calls() -> set[tuple[str, str]]:
    """``(METHOD, normalised path)`` for every call in the UI source."""
    calls: set[tuple[str, str]] = set()
    for src in UI_SRC.rglob("*.js*"):
        if "test" in src.parts:
            continue
        text = src.read_text(encoding="utf-8")
        for m in _HELPER_CALL.finditer(text):
            calls.add((_METHOD[m.group(1)], _normalise(m.group("path"))))
        fetched = set()
        for m in _FETCH_CALL.finditer(text):
            fetched.add(m.start("path"))
            opts = m.group("opts")
            method = re.search(r"method:\s*['\"](\w+)['\"]", opts)
            calls.add(((method.group(1).upper() if method else "GET"), _normalise(m.group("path"))))
        # URLs handed to the browser (downloads, links) rather than fetched
        for m in re.finditer(r"`\$\{getBaseUrl\(\)\}(/[^`]*)`", text):
            if m.start(1) in fetched:
                continue
            calls.add(("GET", _normalise(m.group(1))))
    return calls


def load_coverage() -> dict[str, dict]:
    if not COVERAGE.exists():
        return {}
    return yaml.safe_load(COVERAGE.read_text(encoding="utf-8")) or {}


def problems() -> list[str]:
    ops, calls, cov = operations(), ui_calls(), load_coverage()
    found: list[str] = []
    for key in sorted(set(ops) - set(cov)):
        found.append(f"unclassified operation: {key}")
    for key in sorted(set(cov) - set(ops)):
        found.append(f"ui-coverage.yaml names an operation that does not exist: {key}")
    # The other direction (ENH-09): a UI call that matches no operation is a broken contract.
    known = {(k.split(" ", 1)[0], v) for k, v in ops.items()}
    for method, path in sorted(calls):
        if (method, path) not in known:
            found.append(f"UI calls {method} {path}, which the API does not declare")
    for key, entry in cov.items():
        if key not in ops:
            continue
        status = (entry or {}).get("status")
        if status not in STATUSES:
            found.append(f"{key}: status must be one of {sorted(STATUSES)} (got {status!r})")
            continue
        if status in ("backend-only",) and not entry.get("reason"):
            found.append(f"{key}: backend-only needs a reason")
        if status == "planned" and not entry.get("ref"):
            found.append(f"{key}: planned needs a ref (issue)")
        method, _, _ = key.partition(" ")
        called = (method, ops[key]) in calls
        if entry.get("unscanned"):
            continue  # the UI reaches it through a computed URL the scanner cannot see
        if status in ("surfaced", "partial") and not called:
            found.append(f"{key}: marked {status} but the UI does not call it")
        if status in ("backend-only", "planned") and called:
            found.append(f"{key}: marked {status} but the UI calls it: change it to surfaced or partial")
    return found


def update() -> int:
    ops, cov = operations(), load_coverage()
    calls = ui_calls()
    added = 0
    for key in sorted(ops):
        if key not in cov:
            method = key.split(" ", 1)[0]
            cov[key] = {"status": "surfaced" if (method, ops[key]) in calls else "unclassified"}
            added += 1
    COVERAGE.write_text(
        "# Which API operations the UI uses (QA-04). Checked by scripts/check_ui_coverage.py and tests/test_ui_coverage.py.\n"
        "# status: surfaced | partial (note) | backend-only (reason) | planned (ref: issue)\n"
        + yaml.safe_dump(dict(sorted(cov.items())), sort_keys=False, width=100),
        encoding="utf-8")
    print(f"added {added} entries to {COVERAGE.name}")
    return 0


if __name__ == "__main__":
    if "--update" in sys.argv:
        sys.exit(update())
    issues = problems()
    for line in issues:
        print(line)
    print("ui-coverage: OK" if not issues else f"ui-coverage: {len(issues)} problem(s)")
    sys.exit(1 if issues else 0)
