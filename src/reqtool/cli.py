"""
reqtool.cli
===========
Command-line interface. Thin wrappers over the API client or direct file
operations when the server is not running.
"""

from __future__ import annotations

from .commands.common import cli, _repo_root, _api_base, _get, _post, _server_running
from .commands.scaffold import _write_base_repo, _write_enums, _write_product
from .commands.server import _launch_ui_auto

# Import subcommands to ensure they are registered on the `cli` Click group
from .commands import scaffold, validation, exports, queries, server, users  # noqa: F401

__all__ = [
    "cli",
    "_repo_root",
    "_api_base",
    "_get",
    "_post",
    "_server_running",
    "_write_base_repo",
    "_write_enums",
    "_write_product",
    "_launch_ui_auto",
]

if __name__ == "__main__":
    cli()
