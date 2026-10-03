"""Turn pytest JUnit XML into GitHub annotations and a step summary.

Usage: python scripts/ci_failures.py junit.xml [...]

Prints one ``::error`` workflow command per failed or errored test, so the failing test and its message show
on the check run (and can be read through the API) without opening the raw log, and appends a table to
``$GITHUB_STEP_SUMMARY`` when that variable is set. Always exits 0: it only reports.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def failures(paths: list[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as exc:
            found.append((path, f"could not read JUnit file: {exc}"))
            continue
        for case in root.iter("testcase"):
            for kind in ("failure", "error"):
                node = case.find(kind)
                if node is not None:
                    name = f"{case.get('classname', '')}::{case.get('name', '')}"
                    message = (node.get("message") or node.text or kind).strip()
                    found.append((name, message[:1500]))
    return found


def main(paths: list[str]) -> None:
    found = failures(paths)
    for name, message in found:
        print(f"::error title=Test failed: {_escape(name)}::{_escape(message)}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and found:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Failed tests\n\n| Test | Message |\n|---|---|\n")
            for name, message in found:
                first = message.splitlines()[0].replace("|", "\\|") if message else ""
                fh.write(f"| `{name}` | {first} |\n")
    print(f"{len(found)} failed test(s) reported")


if __name__ == "__main__":
    main(sys.argv[1:])
