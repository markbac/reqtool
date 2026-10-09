"""
reqtool.features.testresults
============================
Ingest JUnit XML from CI and set each requirement's verification status with an evidence link (FEAT-05).

A test case is tied to a requirement when its name, class name or a ``requirement`` property contains the
requirement's human id (for example ``FR-042``). A requirement passes when every test linked to it passes.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from reqtool.fileio import utcnow_iso


class JUnitError(ValueError):
    pass


def parse_junit(xml_text: str) -> list[dict[str, Any]]:
    """``[{name, classname, outcome, text, ids}]``. Rejects DTDs and entities (XML expansion attacks)."""
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", xml_text, re.I):
        raise JUnitError("DTD and entity declarations are not accepted")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise JUnitError(f"Not valid XML: {exc}") from exc
    cases = []
    for tc in root.iter("testcase"):
        outcome = "passed"
        text = ""
        for tag, result in (("failure", "failed"), ("error", "failed"), ("skipped", "skipped")):
            node = tc.find(tag)
            if node is not None:
                outcome, text = result, (node.get("message") or node.text or "").strip()[:300]
                break
        props = {p.get("name"): p.get("value") for p in tc.iter("property")}
        cases.append({"name": tc.get("name", ""), "classname": tc.get("classname", ""),
                      "outcome": outcome, "text": text, "requirement": props.get("requirement", "")})
    return cases


def ingest(store, xml_text: str, source: str = "ci", run_url: str = "") -> dict[str, Any]:
    """Apply results. Returns what changed, which tests matched nothing and which ids are unknown."""
    cases = parse_junit(xml_text)
    by_id = {r.get("id"): uid for uid, r in store.requirement_map().items() if not r.get("deleted") and r.get("id")}
    pattern = re.compile("|".join(re.escape(i) for i in sorted(by_id, key=len, reverse=True))) if by_id else None
    per_req: dict[str, list[dict]] = {}
    unmatched = []
    for c in cases:
        haystack = " ".join([c["name"], c["classname"], c["requirement"]])
        ids = set(pattern.findall(haystack)) if pattern else set()
        if not ids:
            unmatched.append(c["name"])
        for rid in ids:
            per_req.setdefault(by_id[rid], []).append(c)
    updated = []
    for uid, results in per_req.items():
        failed = [c for c in results if c["outcome"] == "failed"]
        skipped = [c for c in results if c["outcome"] == "skipped"]
        status = "failed" if failed else ("in_progress" if skipped and len(skipped) == len(results) else "passed")
        note = f"{len(results)} test(s) from {source}: {len(results) - len(failed) - len(skipped)} passed, {len(failed)} failed"
        if failed:
            note += " -- " + failed[0]["name"] + ": " + failed[0]["text"]
        if run_url:
            note += f" [{run_url}]"
        current = store.requirement_map()[uid].get("verification") or {}
        fields = {"verification": {"status": status, "verified_date": utcnow_iso() if status == "passed" else None,
                                   "note": note}}
        if current.get("status") == status and current.get("note") == note:
            continue
        store.update_requirement(uid, fields, increment="patch", author=source, summary=f"Test results: {status}")
        updated.append({"uid": uid, "id": store.requirement_map()[uid].get("id"), "status": status})
    return {"tests": len(cases), "updated": updated, "unmatched_tests": unmatched}
