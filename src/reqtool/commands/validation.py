"""
reqtool.commands.validation
===========================
Validation and checksum verification subcommands.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
import click

from .common import cli, _repo_root, _get, _server_running


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def validate(repo: Optional[str]):
    """Run full validation suite. Exit 1 on errors."""
    root = Path(repo).resolve() if repo else _repo_root()

    if _server_running():
        result = _get("/validate")
    else:
        from ..store import Store
        from ..validation import validate_all
        store = Store(root)
        store.load()
        result = validate_all(store)

    errors = result.get("errors", [])
    warnings = result.get("warnings", [])

    if warnings:
        click.echo(f"\n{click.style('Warnings', fg='yellow')} ({len(warnings)}):")
        for w in warnings:
            click.echo(f"  [{w.get('uid', '')[:8]}] {w.get('message', '')}")

    if errors:
        click.echo(f"\n{click.style('Errors', fg='red')} ({len(errors)}):")
        for e in errors:
            click.echo(f"  [{e.get('uid', '')[:8]}] {e.get('message', '')}")
        sys.exit(1)
    else:
        click.echo(click.style(f"Validation passed. {len(warnings)} warning(s).", fg="green"))


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def verify(repo: Optional[str]):
    """Verify all content hashes. Exit 1 on mismatch."""
    root = Path(repo).resolve() if repo else _repo_root()
    from ..store import Store
    from ..fileio import (
        compute_requirement_hash, compute_principle_hash,
        compute_tbd_hash,
    )
    store = Store(root)
    store.load()

    failures = []
    for uid, req in store.requirements.items():
        if req.get("deleted"):
            continue
        stored = req.get("content_hash", "")
        computed = compute_requirement_hash(req)
        if stored and stored != computed:
            failures.append(f"requirement {req.get('id', uid)}: hash mismatch")

    for uid, p in store.principles.items():
        stored = p.get("content_hash", "")
        computed = compute_principle_hash(p)
        if stored and stored != computed:
            failures.append(f"principle {p.get('id', uid)}: hash mismatch")

    for uid, t in store.tbds.items():
        stored = t.get("content_hash", "")
        computed = compute_tbd_hash(t)
        if stored and stored != computed:
            failures.append(f"tbd {t.get('id', uid)}: hash mismatch")

    if failures:
        click.echo(click.style("Hash verification FAILED:", fg="red"))
        for f in failures:
            click.echo(f"  {f}")
        sys.exit(1)
    else:
        click.echo(click.style("All hashes verified OK.", fg="green"))
