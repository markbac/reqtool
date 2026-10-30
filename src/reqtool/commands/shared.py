"""
reqtool.commands.shared
=======================
Operating mode and working with a shared remote (#345): ``req mode``, ``req setup``, ``req sync``,
``req finalise-ids``, ``req fix-ids``, ``req merge-file`` (the git merge driver), ``req resolved``,
``req check-changes`` and ``req ci init``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from .common import cli, _repo_root


@cli.command()
@click.argument("new_mode", required=False, type=click.Choice(["local", "server", "shared-repo"]))
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def mode(new_mode: Optional[str], repo: Optional[str]):
    """Show the operating mode, or set the repository's default to NEW_MODE."""
    from ..fileio import load_yaml, save_yaml
    from ..modes import resolve_mode
    root = Path(repo).resolve() if repo else _repo_root()
    cfg_path = root / ".reqtool" / "config.yaml"
    cfg = (load_yaml(cfg_path) or {}) if cfg_path.exists() else {}
    if new_mode:
        if not (root / ".reqtool").is_dir():
            raise click.ClickException(f"{root} is not a reqtool repository")
        cfg["mode"] = new_mode
        save_yaml(cfg_path, cfg)
        click.echo(f"Repository mode set to {new_mode}.")
    effective = resolve_mode(cfg.get("mode"))
    click.echo(f"Operating mode: {effective}" + (" (REQTOOL_MODE override)" if effective != cfg.get("mode", "local") else ""))


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
@click.option("--no-push", is_flag=True, default=False, help="Fetch and pull only.")
def sync(repo: Optional[str], no_push: bool):
    """Fetch, pull, reload and validate, then push. Exit 1 on a conflict or when the pull brought in merge problems (for example duplicate IDs)."""
    import sys
    from ..store import Store
    from ..sync import SyncError, sync_store
    store = Store(Path(repo).resolve() if repo else _repo_root())
    store.load()
    try:
        result = sync_store(store, push_changes=not no_push)
    except SyncError as exc:
        raise click.ClickException(str(exc))
    if result["changed"]:
        click.echo(f"Pulled {len(result['changed'])} changed file(s).")
    for r in result["finalised"]:
        click.echo(f"Finalised {r['old']} as {r['new']}.")
    for e in result["validation"]["merge_errors"]:
        click.echo(click.style("error", fg="red") + f" {e['code']}: {e['message']}")
    click.echo(("Pushed " if result["pushed"] else "Nothing to push on ") + (result["upstream"] or result["branch"]) + ".")
    if result["validation"]["merge_errors"]:
        sys.exit(1)


def _loaded(repo: Optional[str]):
    from ..store import Store
    store = Store(Path(repo).resolve() if repo else _repo_root())
    store.load()
    return store


@cli.command("finalise-ids")
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def finalise_ids(repo: Optional[str]):
    """Give provisional IDs (FR-~1A2B3C4D) their sequential IDs and commit the renames.

    `req sync` does this on the default branch. Run it in CI after a pull request is merged when the
    default branch only accepts changes through pull requests.
    """
    from ..sync import SyncError, as_local_user, finalise_ids as run
    store = _loaded(repo)
    try:
        result = as_local_user(lambda: run(store), store.root)
    except SyncError as exc:
        raise click.ClickException(str(exc))
    for r in result["finalised"]:
        click.echo(f"Finalised {r['old']} as {r['new']}.")
    if not result["finalised"]:
        click.echo("No provisional IDs to finalise.")


@cli.command("fix-ids")
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def fix_ids(repo: Optional[str]):
    """Renumber duplicated IDs: the oldest item keeps the ID, the others get the next free one.
    The renames are recorded in history and left for you to commit."""
    from ..ids import fix_duplicates
    from ..sync import as_local_user
    store = _loaded(repo)
    renamed = as_local_user(lambda: fix_duplicates(store), store.root)
    for r in renamed:
        click.echo(f"Renumbered {r['old']} ({r['uid']}) as {r['new']}.")
    if not renamed:
        click.echo("No duplicate IDs.")


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def setup(repo: Optional[str]):
    """Prepare this clone for sharing: register reqtool's git merge driver and declare it in .gitattributes,
    then report anything else to fix (`req doctor`)."""
    from ..features.doctor import run_doctor
    from ..merge import driver_command, install
    store = _loaded(repo)
    changed = install(store.root, driver_command())
    click.echo("Merge driver registered." if changed else "Merge driver already registered.")
    for c in run_doctor(store)["checks"]:
        click.echo(f"{c['level']} {c['code']}: {c['message']}")


@cli.command("merge-file", hidden=True)
@click.argument("base", type=click.Path())
@click.argument("ours", type=click.Path())
@click.argument("theirs", type=click.Path())
@click.argument("pathname", required=False, default="")
def merge_file(base: str, ours: str, theirs: str, pathname: str):
    """Git merge driver for reqtool YAML (registered by `req setup`). Writes the result into OURS."""
    import sys
    from ..identity import git_identity
    from ..merge import merge_file as run
    me = git_identity(Path.cwd())
    sys.exit(run(Path(base), Path(ours), Path(theirs), pathname, me.name if me else "reqtool"))


@cli.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def resolved(paths: tuple[str, ...], repo: Optional[str]):
    """Mark reqtool files whose merge conflict you resolved by hand: record it in history, fix the hash, stage."""
    from ..identity import git_identity
    from ..merge import mark_resolved
    root = Path(repo).resolve() if repo else _repo_root()
    me = git_identity(root)
    for p in paths:
        try:
            out = mark_resolved(root, Path(p), me.name if me else "reqtool")
        except ValueError as exc:
            raise click.ClickException(str(exc))
        click.echo(f"{out['path']}: resolved as version {out['version']}.")


@cli.command("check-changes")
@click.option("--base", "base_ref", required=True, help="The branch the changes are going into, e.g. origin/main.")
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def check_changes(base_ref: str, repo: Optional[str]):
    """Check that the status moves since BASE follow each item's workflow and its guards. Exit 1 on a problem.
    Run in CI on pull requests, where no server enforces the workflow."""
    import sys
    from ..features.change_check import check_changes as run
    store = _loaded(repo)
    try:
        findings = run(store, base_ref)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    for f in findings:
        click.echo(click.style("error", fg="red") + f" {f['code']}: {f['id'] or f['uid']}: {f['message']}")
    if findings:
        sys.exit(1)
    click.echo(click.style("Status changes follow the workflow.", fg="green"))


@cli.group()
def ci():
    """Continuous-integration set-up for shared repositories."""


@ci.command("init")
@click.option("--repo", default=None, help="Path to the requirements repository root.")
@click.option("--codeowners", default=None,
              help="GitHub user or team (e.g. @org/req-admins) who must review workflow and configuration changes.")
@click.option("--force", is_flag=True, default=False, help="Overwrite files that already exist.")
def ci_init(repo: Optional[str], codeowners: Optional[str], force: bool):
    """Write a GitHub Actions workflow that validates, verifies hashes, checks status moves on pull requests and
    finalises provisional IDs after a merge (and optionally a CODEOWNERS file)."""
    from .. import __version__
    store = _loaded(repo)
    template = Path(__file__).parent.parent / "defaults" / "ci-github-workflow.yaml"
    files = {store.root / ".github" / "workflows" / "reqtool.yml": template.read_text(encoding="utf-8")
             .replace("@DEFAULT_BRANCH@", store.config.git.default_branch).replace("@REQTOOL_VERSION@", __version__)}
    if codeowners:
        files[store.root / ".github" / "CODEOWNERS"] = (
            "# Written by `req ci init`: workflow, rules and configuration changes need an administrator's review,\n"
            "# as they would on a reqtool server.\n"
            f"/.reqtool/ {codeowners}\n/.github/ {codeowners}\n/.gitattributes {codeowners}\n")
    for path, text in files.items():
        rel = path.relative_to(store.root)
        if path.exists() and not force:
            click.echo(f"{rel} exists; use --force to overwrite.")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        click.echo(f"Wrote {rel}.")
    click.echo("Commit them, then make the `reqtool / check` job a required status check on "
               f"{store.config.git.default_branch} and turn on required reviews.")
