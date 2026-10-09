"""
reqtool.commands.features
=========================
``req gate``, ``req doctor``, ``req query``, ``req test-results`` and ``req snapshot`` (FEAT-01/05/07/09/11).
These read the repository files directly, so they need no server.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from .common import cli, _repo_root


def _store(repo: Optional[str]):
    from ..store import Store
    store = Store(Path(repo).resolve() if repo else _repo_root())
    store.load()
    return store


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
@click.option("--product", default=None, help="Limit the gate to one product.")
def gate(repo: Optional[str], product: Optional[str]):
    """Release readiness gate. Exit 1 when open TBDs, unverified safety items, suspect links, trace gaps
    or uncommitted changes would make a release unsafe."""
    from ..features.insight import release_readiness
    result = release_readiness(_store(repo), product)
    for f in result["findings"]:
        click.echo(f"{f['code']}: {f['id']}: {f['message']}")
    if result["ready"]:
        click.echo(click.style("Release gate passed.", fg="green"))
        return
    click.echo(click.style(f"Release gate failed: {result['count']} finding(s).", fg="red"))
    sys.exit(1)


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def doctor(repo: Optional[str]):
    """Check configuration, secrets hygiene, dependencies, hierarchy sanity and stray files. Exit 1 on errors."""
    from ..features.doctor import run_doctor
    result = run_doctor(_store(repo))
    for c in result["checks"]:
        colour = "red" if c["level"] == "error" else "yellow"
        click.echo(f"{click.style(c['level'], fg=colour)} {c['code']}: {c['message']}")
    if result["ok"]:
        click.echo(click.style(f"Doctor found no errors ({result['warnings']} warning(s)).", fg="green"))
        return
    sys.exit(1)


@cli.command()
@click.argument("expression")
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def query(expression: str, repo: Optional[str]):
    """Find requirements, for example: req query 'status:approved no:verification'."""
    from ..features import query as q
    try:
        found = q.run(_store(repo).requirement_map(), expression)
    except q.QueryError as exc:
        raise click.ClickException(str(exc))
    for r in found:
        click.echo(f"{r.get('id', r['uid'])}\t{r.get('status', '')}\t{r.get('title', '')}")
    click.echo(f"{len(found)} match(es)", err=True)


@cli.command("test-results")
@click.argument("junit_xml", type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", default=None, help="Path to the requirements repository root.")
@click.option("--source", default="ci", help="Label recorded with the result.")
@click.option("--run-url", default="", help="Link to the CI run, kept as evidence.")
def test_results(junit_xml: str, repo: Optional[str], source: str, run_url: str):
    """Set verification status from a JUnit XML file. Tests name a requirement id such as FR-042."""
    from ..features import testresults
    try:
        result = testresults.ingest(_store(repo), Path(junit_xml).read_text(encoding="utf-8"), source, run_url)
    except testresults.JUnitError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"{result['tests']} test(s), {len(result['updated'])} requirement(s) updated, "
               f"{len(result['unmatched_tests'])} test(s) matched no requirement")
    for u in result["updated"]:
        click.echo(f"  {u['id']}: {u['status']}")


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
@click.option("--baseline", default=None, help="Baseline name (default: the files on disk).")
@click.option("--out", "out_dir", default="snapshot", show_default=True, help="Output folder.")
def snapshot(repo: Optional[str], baseline: Optional[str], out_dir: str):
    """Write a read-only static HTML site for stakeholders (search, traceability, diff to the previous baseline)."""
    from ..features.snapshot import build_site
    try:
        info = build_site(_store(repo), Path(out_dir).resolve(), baseline)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Wrote {info['requirements']} requirement page(s) to {info['out']}")
