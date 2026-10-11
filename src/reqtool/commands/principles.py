"""
reqtool.commands.principles
===========================
``req principles``: list the default principle packs and add them to a repository.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from .common import cli, _repo_root


@cli.group()
def principles():
    """Engineering principles, grouped by area and category."""


@principles.command("packs")
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def principles_packs(repo: Optional[str]):
    """List the default packs and how many of their principles this repository has."""
    from ..services.principles import PrincipleService
    from ..store import Store
    store = Store(Path(repo).resolve() if repo else _repo_root())
    store.load()
    for pack in PrincipleService(store).packs():
        click.echo(f"{pack['area']:<22} {pack['label']:<24} {pack['installed']:>3} of {pack['count']:<3} installed")
        click.echo("    " + ", ".join(f"{c['label']} ({c['count']})" for c in pack["categories"] if c["count"]))


@principles.command("add-pack")
@click.argument("areas", nargs=-1, required=True)
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def principles_add_pack(areas: tuple[str, ...], repo: Optional[str]):
    """Add one or more packs (AREAS, or 'all'). Principles already in the repository are left alone."""
    from ..principles import pack_areas
    from ..services.errors import ServiceError
    from ..services.principles import PrincipleService
    from ..store import Store
    store = Store(Path(repo).resolve() if repo else _repo_root())
    store.load()
    service = PrincipleService(store)
    wanted = pack_areas() if "all" in areas else list(areas)
    for area in wanted:
        try:
            result = service.add_pack(area)
        except ServiceError as exc:
            raise click.ClickException(exc.message) from None
        click.echo(f"{area}: added {result['added']}, already present {result['skipped']}")


@principles.command("place")
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def principles_place(repo: Optional[str]):
    """Give principles that have no area and category one (also done by 'req migrate')."""
    from ..services.principles import PrincipleService
    from ..store import Store
    store = Store(Path(repo).resolve() if repo else _repo_root())
    store.load()
    result = PrincipleService(store).place_existing()
    click.echo(f"Placed {result['placed']} principle(s).")
    if result["unplaced"]:
        click.echo("No area could be worked out for: " + ", ".join(sorted(result["unplaced"])))
