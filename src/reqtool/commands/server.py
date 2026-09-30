"""
reqtool.commands.server
=======================
Server subcommand (serve) and UI launcher helper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional
import click

from .common import cli, _repo_root


def _launch_ui_auto(host: str, port: int, is_app: bool) -> None:
    import time
    import threading
    import webbrowser
    import subprocess
    import shutil

    def _worker():
        time.sleep(1.0)
        url = f"http://{host}:{port}"
        if is_app:
            for browser_cmd in ["msedge", "chrome", "google-chrome", "brave", "chromium"]:
                cmd_path = shutil.which(browser_cmd)
                if cmd_path:
                    try:
                        subprocess.Popen([cmd_path, f"--app={url}"])
                        return
                    except Exception:
                        pass
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, show_default=True)
@click.option("--reload", is_flag=True, default=False, help="Enable uvicorn auto-reload (dev).")
@click.option("--browser", is_flag=True, default=False, help="Auto-launch default web browser.")
@click.option("--app", is_flag=True, default=False, help="Auto-launch desktop application window.")
def serve(repo: Optional[str], host: str, port: int, reload: bool, browser: bool, app: bool):
    """Start the backend API and UI server."""
    import uvicorn
    from .. import __version__
    from ..store import Store

    root = Path(repo).resolve() if repo else _repo_root()
    os.environ["REQTOOL_REPO"] = str(root)

    if browser or app:
        import reqtool.cli
        reqtool.cli._launch_ui_auto(host, port, is_app=app)

    try:
        _store = Store(root)
        _store.load()
        _req_count = len([r for r in _store.requirements.values() if not r.get("deleted")])
        _principle_count = len([p for p in _store.principles.values() if not p.get("deleted")])
        _tbd_count = len([t for t in _store.tbds.values() if not t.get("deleted")])
        _repo_title = _store.config.repo_title or _store.config.repo_id or root.name
        _has_ui = (Path(__file__).parent.parent / "ui" / "dist").exists()
        _type_count = len(_store.hierarchy.types)
        del _store
    except Exception:
        _req_count = _principle_count = _tbd_count = _type_count = 0
        _repo_title = root.name
        _has_ui = False

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    W = 58
    SEP = click.style("-" * W, fg="bright_black")
    def _row(label: str, value: str, value_colour: str = "white") -> None:
        padded = f"  {label:<20}"
        click.echo(padded + click.style(value, fg=value_colour))

    click.echo("")
    click.echo(SEP)
    click.echo(click.style(f"  reqtool  v{__version__}", fg="cyan", bold=True))
    click.echo(SEP)
    _row("Repository",   _repo_title,          "bright_white")
    _row("Root",         str(root),             "bright_black")
    click.echo("")
    _row("Requirements", str(_req_count),       "bright_white")
    _row("Principles",   str(_principle_count), "bright_white")
    _row("TBDs",         str(_tbd_count),       "bright_white")
    _row("Types loaded", str(_type_count),      "bright_white")
    click.echo("")
    base_url = f"http://{host}:{port}"
    _row("URL",          base_url,              "bright_cyan")
    _row("API docs",     f"{base_url}/docs",    "bright_cyan")
    _row("Health",       f"{base_url}/health",  "bright_cyan")
    _row("Badge",        f"{base_url}/badge/validated", "bright_cyan")
    ui_status = click.style("ready", fg="bright_green") if _has_ui else click.style("not built  (run: cd src/reqtool/ui && npm install && npm run build)", fg="yellow")
    click.echo(f"  {'React UI':<20}" + ui_status)
    if reload:
        click.echo("")
        click.echo("  " + click.style("[!] auto-reload enabled (dev mode)", fg="yellow"))
    click.echo(SEP)
    click.echo(click.style("  Press Ctrl+C to stop.", fg="bright_black"))
    click.echo("")

    if reload:
        uvicorn.run(
            "reqtool.main:app_factory",
            host=host,
            port=port,
            reload=True,
            factory=True,
            log_level="info",
        )
    else:
        from ..api import create_app
        app_instance = create_app(root)
        uvicorn.run(
            app_instance,
            host=host,
            port=port,
            log_level="info",
        )
