"""
reqtool.commands.users
======================
`req user` subcommands: manage accounts directly in .reqtool/users.yaml.
This is how the first administrator is created (no default account exists).
"""

from __future__ import annotations

import click

from .common import cli, _repo_root


@cli.group()
def user():
    """Manage reqtool user accounts."""


@user.command("add")
@click.argument("username")
@click.option("--role", type=click.Choice(["admin", "editor", "viewer"]), default="editor", show_default=True)
@click.option("--full-name", default="")
@click.option("--email", default="")
@click.option("--password", default=None, help="Omit to be prompted (recommended).")
@click.option("--repo", default=None)
def user_add(username, role, full_name, email, password, repo):
    """Create an account (use --role admin for the first administrator)."""
    from pathlib import Path
    from ..auth import UserStore
    root = Path(repo).resolve() if repo else _repo_root()
    if password is None:
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    if len(password) < 8:
        raise click.ClickException("Password must be at least 8 characters.")
    try:
        UserStore(root).create_user(username, password, full_name, email, role)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Created {role} '{username}'.")


@user.command("passwd")
@click.argument("username")
@click.option("--password", default=None, help="Omit to be prompted (recommended).")
@click.option("--repo", default=None)
def user_passwd(username, password, repo):
    """Reset a user's password."""
    from pathlib import Path
    from ..auth import UserStore
    root = Path(repo).resolve() if repo else _repo_root()
    if password is None:
        password = click.prompt("New password", hide_input=True, confirmation_prompt=True)
    if len(password) < 8:
        raise click.ClickException("Password must be at least 8 characters.")
    try:
        UserStore(root).update_user(username, {"password": password})
    except KeyError as exc:
        raise click.ClickException(str(exc.args[0]))
    click.echo(f"Password updated for '{username}'.")


@user.command("list")
@click.option("--repo", default=None)
def user_list(repo):
    """List accounts."""
    from pathlib import Path
    from ..auth import UserStore
    root = Path(repo).resolve() if repo else _repo_root()
    users = UserStore(root).load_users()
    if not users:
        click.echo("No users. Create one with: req user add <name> --role admin")
    for u in users.values():
        click.echo(f"{u['username']}\t{u.get('role', 'editor')}")
