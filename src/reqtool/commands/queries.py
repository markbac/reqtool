"""
reqtool.commands.queries
========================
Querying and creation subcommands (show, history, diff, stats, new, new_agile).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional
import click

from .common import cli, _repo_root, _get, _post, _server_running


# ---------------------------------------------------------------------------
# new_agile
# ---------------------------------------------------------------------------

@cli.group()
def new_agile():
    """Create a new agile item (story, task, bug, spike, epic, feature, theme, initiative)."""


def _make_agile_item(repo: Optional[str], item_type: str) -> None:
    """Shared logic for creating any agile item type interactively."""
    root = Path(repo).resolve() if repo else _repo_root()
    from ..store import Store
    store = Store(root)
    store.load()

    suggested_id = store.next_id_for_type(item_type)
    item_id = click.prompt("ID", default=suggested_id)
    title = click.prompt("Title")
    owner = click.prompt("Owner", default="")
    assignee = click.prompt("Assignee", default="")
    iteration = click.prompt("Iteration", default="")
    estimate_str = click.prompt("Estimate", default="")

    fields: dict = {
        "id": item_id,
        "title": title,
        "req_type": item_type,
        "owner": owner or None,
        "assignee": assignee or None,
        "iteration": iteration or None,
    }
    if estimate_str:
        try:
            fields["estimate"] = float(estimate_str)
        except ValueError:
            pass

    req = store.create_requirement(fields)
    click.echo(click.style(f"Created {item_type}: {req['id']} ({req['uid'][:8]})", fg="green"))


for _atype in ("story", "task", "bug", "spike", "epic", "feature", "theme", "initiative"):
    def _make_cmd(atype=_atype):
        @new_agile.command(atype)
        @click.option("--repo", default=None)
        def _cmd(repo: Optional[str]):
            f"""Create a new {atype}."""
            _make_agile_item(repo, atype)
        _cmd.__name__ = f"new_{atype}"
        return _cmd
    _make_cmd()


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

@cli.group()
def new():
    """Create a new artefact interactively."""


@new.command("requirement")
@click.option("--repo", default=None)
def new_requirement(repo: Optional[str]):
    """Create a new requirement interactively."""
    root = Path(repo).resolve() if repo else _repo_root()
    req_id = click.prompt("ID (e.g. REQ-SYS-001)")
    title = click.prompt("Title")
    description = click.prompt("Description (shall statement)")
    owner = click.prompt("Owner", default="")
    domain = click.prompt("Domain", default="")

    fields = {
        "id": req_id,
        "title": title,
        "content": {"description": description, "rationale": "", "extended_description": ""},
        "owner": owner or None,
        "domain": domain or None,
    }

    if _server_running():
        result = _post("/requirements", fields)
    else:
        from ..store import Store
        store = Store(root)
        store.load()
        result = store.create_requirement(fields)

    click.echo(click.style(f"Created: {result['id']} ({result['uid']})", fg="green"))


@new.command("principle")
@click.option("--repo", default=None)
def new_principle(repo: Optional[str]):
    """Create a new principle interactively."""
    root = Path(repo).resolve() if repo else _repo_root()
    p_id = click.prompt("ID (e.g. P-LOGGING)")
    title = click.prompt("Title")
    description = click.prompt("Principle statement")

    fields = {
        "id": p_id,
        "title": title,
        "content": {"description": description, "rationale": "", "implications": "", "exceptions": ""},
    }

    if _server_running():
        result = _post("/principles", fields)
    else:
        from ..store import Store
        store = Store(root)
        store.load()
        result = store.create_principle(fields)

    click.echo(click.style(f"Created: {result['id']} ({result['uid']})", fg="green"))


@new.command("tbd")
@click.option("--repo", default=None)
def new_tbd(repo: Optional[str]):
    """Create a new TBD interactively."""
    root = Path(repo).resolve() if repo else _repo_root()
    tbd_id = click.prompt("ID (e.g. TBD-042)")
    title = click.prompt("Title")
    description = click.prompt("Description (what is unknown and why it matters)")

    fields = {
        "id": tbd_id,
        "title": title,
        "content": {"description": description, "impact": "", "resolution_criteria": "", "resolution": None},
    }

    if _server_running():
        result = _post("/tbds", fields)
    else:
        from ..store import Store
        store = Store(root)
        store.load()
        result = store.create_tbd(fields)

    click.echo(click.style(f"Created: {result['id']} ({result['uid']})", fg="green"))


# ---------------------------------------------------------------------------
# show & history
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("id_or_uid")
@click.option("--repo", default=None)
def show(id_or_uid: str, repo: Optional[str]):
    """Print an artefact to stdout."""
    root = Path(repo).resolve() if repo else _repo_root()

    from ..store import Store
    store = Store(root)
    store.load()
    for collection in (store.requirements, store.principles, store.decisions):
        for uid, item in collection.items():
            if uid == id_or_uid or item.get("id") == id_or_uid:
                click.echo(json.dumps(item, indent=2, default=str))
                return

    if _server_running():
        for endpoint in ("/requirements", "/principles", "/tbds"):
            try:
                items = _get(endpoint)
                for item in items:
                    if item.get("uid") == id_or_uid or item.get("id") == id_or_uid:
                        click.echo(json.dumps(item, indent=2, default=str))
                        return
            except Exception:
                pass

    click.echo(f"Not found: {id_or_uid}", err=True)
    sys.exit(1)


@cli.command()
@click.argument("id_or_uid")
@click.option("--repo", default=None)
def history(id_or_uid: str, repo: Optional[str]):
    """Print git log for an artefact."""
    root = Path(repo).resolve() if repo else _repo_root()
    from ..store import Store
    from ..git_ops import git_log
    store = Store(root)
    store.load()

    uid = None
    for collection in (store.requirements, store.principles, store.decisions):
        for item_uid, item in collection.items():
            if item_uid == id_or_uid or item.get("id") == id_or_uid:
                uid = item_uid
                break
        if uid:
            break

    if uid is None:
        click.echo(f"Not found: {id_or_uid}", err=True)
        sys.exit(1)

    for get_path in (store.req_path, store.principle_path, store.decision_path):
        p = get_path(uid)
        if p.exists():
            entries = git_log(root, p)
            for e in entries:
                click.echo(f"{e['sha'][:7]}  {e['date'][:10]}  {e['author_name']}  {e['subject']}")
            return

    click.echo("No git history found (file not yet committed).")


# ---------------------------------------------------------------------------
# diff & stats
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--since", default="HEAD~1", help="Git ref to diff against (commit SHA, tag, or HEAD~N).")
@click.option("--repo", default=None)
def diff(since: str, repo: Optional[str]):
    """Show requirement changes since a git ref."""
    root = Path(repo).resolve() if repo else _repo_root()
    result = _get(f"/diff?since={since}")

    if not result.get("changes"):
        click.echo(click.style(f"No requirement changes since {since}", fg="green"))
        return

    total = result.get("total", 0)
    click.echo(click.style(f"{total} change(s) since {since}", bold=True))
    click.echo()

    for c in result["changes"]:
        action = c["action"]
        if action == "added":
            click.echo(click.style(f"  + {c['id']}", fg="green") + f"  {c.get('title','')}")
        elif action == "deleted":
            click.echo(click.style(f"  - {c['id']}", fg="red"))
        elif action == "changed":
            click.echo(click.style(f"  ~ {c['id']}", fg="yellow") +
                       f"  v{c.get('version_from','?')} -> v{c.get('version_to','?')}")
            for field, delta in c.get("changes", {}).items():
                from_s = str(delta.get("from",""))[:60]
                to_s   = str(delta.get("to",""))[:60]
                click.echo(f"      {field}:")
                click.echo(click.style(f"        - {from_s}", fg="red"))
                click.echo(click.style(f"        + {to_s}", fg="green"))


@cli.command()
@click.option("--repo", default=None)
def stats(repo: Optional[str]):
    """Print a quick metrics summary to stdout."""
    root = Path(repo).resolve() if repo else _repo_root()
    data = _get("/metrics")

    totals = data.get("totals", {})
    status = data.get("status", {})
    gaps   = data.get("quality_gaps", {})
    funnel = data.get("approval_funnel", {})
    vel    = data.get("velocity", {})

    click.echo(click.style("Requirements", bold=True))
    click.echo(f"  Total:        {totals.get('requirements', 0)}")
    click.echo(f"  Principles:   {totals.get('principles', 0)}")
    click.echo(f"  Open TBDs:    {totals.get('open_tbds', 0)}")
    click.echo()

    click.echo(click.style("Status", bold=True))
    for s, n in sorted(status.items(), key=lambda x: -x[1]):
        bar = "█" * min(n, 40)
        click.echo(f"  {s:<16} {n:>4}  {bar}")
    click.echo(f"  Approval rate: {funnel.get('approval_rate_pct', 0)}%")
    click.echo()

    click.echo(click.style("Quality gaps", bold=True))
    req_total = totals.get("requirements", 1)
    for gap, n in gaps.items():
        pct = round(n / req_total * 100) if req_total else 0
        colour = "red" if n > 0 else "green"
        click.echo(click.style(f"  {gap.replace('_',' '):<24} {n:>4} ({pct}%)", fg=colour))
    click.echo()

    click.echo(click.style("Activity", bold=True))
    click.echo(f"  Changes last 30d: {vel.get('changes_last_30d', 0)}")
