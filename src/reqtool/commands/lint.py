"""
reqtool.commands.lint
=====================
``req lint``: check requirement text for glossary, wordy-phrase, acronym and vague-term problems.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from .common import cli, _repo_root


@cli.command("lint")
@click.option("--repo", default=None, help="Path to the requirements repository root.")
@click.option("--fail-on", type=click.Choice(["error", "warning", "info", "never"]), default="error",
              show_default=True, help="Exit 1 when a finding is at least this serious.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", show_default=True)
def lint_command(repo: Optional[str], fail_on: str, fmt: str):
    """Check requirement text against .reqtool/lint.yaml (and Vale, if enabled there)."""
    from ..services.lint import LintService
    from ..store import Store
    root = Path(repo).resolve() if repo else _repo_root()
    store = Store(root)
    store.load()
    service = LintService(store)
    linter, report = service.report()
    if not linter.config.enabled:
        click.echo("The writing check is switched off in .reqtool/lint.yaml.")
        return
    if fmt == "json":
        click.echo(json.dumps({"summary": report.summary(), "issues": [i.as_dict() for i in report.issues]}, indent=2))
    else:
        for i in report.issues:
            tip = f" (suggestion: {i.suggestion})" if i.suggestion else ""
            click.echo(f"{i.id or i.uid[:8]} {i.field}:{i.line}: {i.severity} {i.rule} {i.message}{tip}")
        s = report.summary()
        colour = "green" if not s["issues"] else "yellow"
        click.echo(click.style(f"{s['issues']} finding(s) in {s['items_with_issues']} of {s['items']} item(s).", fg=colour))
    if fail_on != "never" and report.count(fail_on):
        sys.exit(1)
