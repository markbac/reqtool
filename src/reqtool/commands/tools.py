"""
reqtool.commands.tools
======================
``req tools``: check the tools reqtool uses and install the ones it can (Vale).
"""

from __future__ import annotations

import sys
from typing import Optional

import click

from .common import cli


@cli.command("tools")
@click.option("--check", "check_only", is_flag=True, help="Only report what is installed.")
@click.option("--force", is_flag=True, help="Try the download again even if the last attempt failed.")
@click.option("--vale-version", default=None, help="Install this Vale version instead of the latest.")
@click.option("--quiet", is_flag=True, help="Print only problems (for setup scripts).")
def tools_command(check_only: bool, force: bool, vale_version: Optional[str], quiet: bool):
    """Check for Python, git, Node.js and Vale, and install Vale if it is missing.

    Vale is downloaded from its GitHub release, verified against the published checksum, and kept in
    ~/.reqtool/tools (set REQTOOL_TOOLS_DIR to move it). Exits 1 only when a required tool (Python, git) is missing.
    """
    from ..tooling import ensure_tools
    statuses = ensure_tools(install=not check_only, vale_version_wanted=vale_version, force=force)
    failed = False
    for s in statuses:
        if s.ok and quiet:
            continue
        mark = "ok     " if s.ok else ("MISSING" if s.required else "absent ")
        click.echo(f"{mark} {s.name:<7} {s.detail}", err=not s.ok and quiet)
        failed = failed or (s.required and not s.ok)
    sys.exit(1 if failed else 0)
