"""
reqtool.commands.exports
========================
Export and import subcommands (JSX, Markdown, CSV, OpenAPI, module import).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
import click

from .common import cli, _repo_root


@cli.group()
def export():
    """Export requirements to various formats."""


@export.command("jsx")
@click.option("--product", default=None, help="Product ID filter.")
@click.option("--repo", default=None)
def export_jsx(product: Optional[str], repo: Optional[str]):
    """Export JSX viewer component."""
    root = Path(repo).resolve() if repo else _repo_root()
    from ..store import Store
    from ..exports import export_jsx as _export_jsx
    store = Store(root)
    store.load()
    content = _export_jsx(store, product)
    out_dir = root / store.config.export.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "requirements.jsx"
    out_path.write_text(content, encoding="utf-8")
    click.echo(f"Written: {out_path}")


@export.command("markdown")
@click.option("--product", default=None)
@click.option("--split-by", default=None, help="domain | product | none")
@click.option("--repo", default=None)
def export_markdown(product: Optional[str], split_by: Optional[str], repo: Optional[str]):
    """Export Markdown files."""
    root = Path(repo).resolve() if repo else _repo_root()
    from ..store import Store
    from ..exports import export_markdown as _export_md
    store = Store(root)
    store.load()
    files = _export_md(store, product_id=product, split_by=split_by)
    out_dir = root / store.config.export.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        p = out_dir / filename
        p.write_text(content, encoding="utf-8")
        click.echo(f"Written: {p}")


@export.command("csv")
@click.option("--product", default=None)
@click.option("--repo", default=None)
def export_csv_cmd(product: Optional[str], repo: Optional[str]):
    """Export CSV."""
    root = Path(repo).resolve() if repo else _repo_root()
    from ..store import Store
    from ..exports import export_csv as _export_csv
    store = Store(root)
    store.load()
    content = _export_csv(store, product_id=product)
    out_dir = root / store.config.export.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "requirements.csv"
    out_path.write_bytes(content.encode("utf-8"))
    click.echo(f"Written: {out_path}")


@export.command("adr")
@click.option("--repo", default=None)
def export_adr_cmd(repo: Optional[str]):
    """Export Architecture Decision Records (ADR) as Markdown."""
    root = Path(repo).resolve() if repo else _repo_root()
    from ..store import Store
    from ..exports import export_adr_markdown
    store = Store(root)
    store.load()
    content = export_adr_markdown(store)
    out_dir = root / store.config.export.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "architecture_decision_records.md"
    out_path.write_text(content, encoding="utf-8")
    click.echo(f"Written: {out_path}")


@cli.command("import")
@click.argument("module_id")
@click.option("--product", default="", help="Product ID to lock against (default: all referencing products)")
@click.option("--repo", default=None)
def import_module(module_id: str, product: str, repo: Optional[str]):
    """Import/update a module and write the lock file."""
    root = Path(repo).resolve() if repo else _repo_root()
    from ..store import Store
    store = Store(root)
    store.load()

    if module_id not in store.modules:
        click.echo(f"Module '{module_id}' not found in {root / 'modules'}", err=True)
        sys.exit(1)

    if product:
        products_to_lock = [product]
    else:
        products_to_lock = [
            pid for pid, prod in store.products.items()
            if any(m.get("id") == module_id for m in prod.get("modules", []))
        ]
        if not products_to_lock:
            click.echo(f"Module '{module_id}' is not referenced by any product.", err=True)
            sys.exit(1)

    for pid in products_to_lock:
        try:
            lock = store.import_module(pid, module_id)
            click.echo(click.style(f"Lock written: products/{pid}/_product.lock ({len(lock['locked'])} module(s))", fg="green"))
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)


@cli.command()
@click.option("--output", "-o", default="openapi.yaml", show_default=True, help="Output file path.")
@click.option("--format", "fmt", type=click.Choice(["yaml", "json"]), default="yaml", show_default=True)
@click.option("--repo", default=None)
def openapi(output: str, fmt: str, repo: Optional[str]):
    """Export the OpenAPI specification to a file."""
    root = Path(repo).resolve() if repo else _repo_root()
    from reqtool.api import create_app
    app = create_app(root)
    schema = app.openapi()

    out_path = Path(output)
    if fmt == "yaml":
        try:
            import ruamel.yaml as ryaml
            yml = ryaml.YAML()
            yml.default_flow_style = False
            yml.width = 120
            with out_path.open("w", encoding="utf-8") as f:
                yml.dump(schema, f)
        except ImportError:
            import json
            click.echo("ruamel.yaml not available, falling back to JSON", err=True)
            out_path = out_path.with_suffix(".json")
            out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    else:
        import json
        out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    click.echo(click.style(f"OpenAPI spec written: {out_path}", fg="green"))
    click.echo(f"  Paths: {len(schema.get('paths', {}))}")
    click.echo(f"  Version: {schema.get('info', {}).get('version', '?')}")
