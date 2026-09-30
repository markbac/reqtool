"""
reqtool.commands.common
=======================
Common CLI utilities, root helpers, HTTP wrappers, and root Click group.
"""

from __future__ import annotations

import os
from pathlib import Path
import click


# Default repo root: cwd or REQTOOL_REPO env var
def _repo_root() -> Path:
    env = os.environ.get("REQTOOL_REPO")
    if env:
        return Path(env).resolve()
    return Path.cwd()


def _api_base() -> str:
    return os.environ.get("REQTOOL_API", "http://localhost:8765")


def _get(path: str) -> dict:
    import httpx
    resp = httpx.get(f"{_api_base()}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, data: dict) -> dict:
    import httpx
    resp = httpx.post(f"{_api_base()}{path}", json=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _server_running() -> bool:
    try:
        import httpx
        httpx.get(f"{_api_base()}/enums/core", timeout=2)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """reqtool -- requirements management for engineering programmes."""
