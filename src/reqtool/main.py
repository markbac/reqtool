"""
reqtool.main
============
ASGI application factory for uvicorn.
Used by: uvicorn reqtool.main:app_factory --factory
"""

from __future__ import annotations

import os
from pathlib import Path

from .api import create_app


def app_factory():
    """Factory function for uvicorn --factory mode."""
    repo = os.environ.get("REQTOOL_REPO", str(Path.cwd()))
    return create_app(Path(repo))
