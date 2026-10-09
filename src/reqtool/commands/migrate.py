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


def migrate_settings(root: Path) -> list[str]:
    """Give an older repository its own workflow and writing-check files. Existing files are never changed."""
    from ..repo_init import write_hierarchy_file, write_lint_file
    written = []
    reqtool_dir = root / ".reqtool"
    if reqtool_dir.is_dir():
        if not (reqtool_dir / "hierarchy.yaml").exists():
            write_hierarchy_file(root)
            written.append(".reqtool/hierarchy.yaml")
        if not (reqtool_dir / "lint.yaml").exists():
            write_lint_file(root)
            written.append(".reqtool/lint.yaml")
    return written


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def migrate(repo: Optional[str]):
    """Migrate legacy layouts: TBDs move into decisions/, and the repository gets its own workflow and lint files."""
    root = Path(repo).resolve() if repo else _repo_root()
    result = migrate_tbds(root)
    click.echo(f"TBDs moved to decisions/: {result['moved']}")
    if result["skipped"]:
        click.echo(f"{result['skipped']} file(s) differ from the copy in decisions/ and were left in tbds/ -- reconcile them by hand.")
    for name in migrate_settings(root):
        click.echo(f"Wrote {name} (the repository now owns these settings).")
