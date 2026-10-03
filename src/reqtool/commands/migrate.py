"""
reqtool.commands.migrate
========================
``req migrate``: bring an older repository up to the current layout.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import click

from .common import cli, _repo_root


def migrate_tbds(root: Path) -> dict[str, int]:
    """Move ``tbds/*.yaml`` into ``decisions/``. Safe to run again: moved files are not touched twice."""
    src, dst = root / "tbds", root / "decisions"
    moved = skipped = 0
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for path in sorted(src.glob("*.yaml")):
            target = dst / path.name
            if target.exists():
                if target.read_bytes() == path.read_bytes():
                    path.unlink()  # identical copy already migrated
                else:
                    skipped += 1  # differing file: leave both for a person to reconcile
                continue
            shutil.move(str(path), str(target))
            moved += 1
        try:
            src.rmdir()
        except OSError:
            pass  # not empty (skipped files, other content)
    return {"moved": moved, "skipped": skipped}


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def migrate(repo: Optional[str]):
    """Migrate legacy layouts: TBDs move from tbds/ into decisions/."""
    root = Path(repo).resolve() if repo else _repo_root()
    result = migrate_tbds(root)
    click.echo(f"TBDs moved to decisions/: {result['moved']}")
    if result["skipped"]:
        click.echo(f"{result['skipped']} file(s) differ from the copy in decisions/ and were left in tbds/ -- reconcile them by hand.")
