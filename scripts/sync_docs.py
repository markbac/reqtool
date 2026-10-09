#!/usr/bin/env python3
"""Keep one source of truth for documents that are published twice (QA-05 / ARC-15).

The root copy is canonical. ``docs/`` holds a copy for the site build.

    python scripts/sync_docs.py          # overwrite docs/ copies from the root
    python scripts/sync_docs.py --check  # exit 1 if they differ
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ("CONTRIBUTING.md",)


def out_of_sync() -> list[str]:
    return [n for n in SHARED if (ROOT / n).read_bytes() != (ROOT / "docs" / n).read_bytes()]


if __name__ == "__main__":
    stale = out_of_sync()
    if "--check" in sys.argv:
        for n in stale:
            print(f"docs/{n} differs from {n}: run python scripts/sync_docs.py")
        sys.exit(1 if stale else 0)
    for n in stale:
        (ROOT / "docs" / n).write_bytes((ROOT / n).read_bytes())
        print(f"updated docs/{n}")
