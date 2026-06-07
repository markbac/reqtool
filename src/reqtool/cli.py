"""
reqtool.cli
===========
Command-line interface. Thin wrappers over the API client or direct file
operations when the server is not running.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

# Default repo root: cwd or REQTOOL_REPO env var
def _repo_root() -> Path:
    env = os.environ.get("REQTOOL_REPO")
    if env:
        return Path(env).resolve()
    return Path.cwd()


def _api_base() -> str:
    return os.environ.get("REQTOOL_API", "http://localhost:8765")


def _get(path: str) -> dict:
    import httpx
    resp = httpx.get(f"{_api_base()}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, data: dict) -> dict:
    import httpx
    resp = httpx.post(f"{_api_base()}{path}", json=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _server_running() -> bool:
    try:
        import httpx
        httpx.get(f"{_api_base()}/enums/core", timeout=2)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """reqtool -- requirements management for engineering programmes."""


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def validate(repo: Optional[str]):
    """Run full validation suite. Exit 1 on errors."""
    root = Path(repo).resolve() if repo else _repo_root()

    if _server_running():
        result = _get("/validate")
    else:
        from .store import Store
        from .validation import validate_all
        store = Store(root)
        store.load()
        result = validate_all(store)

    errors = result.get("errors", [])
    warnings = result.get("warnings", [])

    if warnings:
        click.echo(f"\n{click.style('Warnings', fg='yellow')} ({len(warnings)}):")
        for w in warnings:
            click.echo(f"  [{w.get('uid', '')[:8]}] {w.get('message', '')}")

    if errors:
        click.echo(f"\n{click.style('Errors', fg='red')} ({len(errors)}):")
        for e in errors:
            click.echo(f"  [{e.get('uid', '')[:8]}] {e.get('message', '')}")
        sys.exit(1)
    else:
        click.echo(click.style(f"Validation passed. {len(warnings)} warning(s).", fg="green"))


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def verify(repo: Optional[str]):
    """Verify all content hashes. Exit 1 on mismatch."""
    root = Path(repo).resolve() if repo else _repo_root()
    from .store import Store
    from .fileio import (
        compute_requirement_hash, compute_principle_hash,
        compute_tbd_hash,
    )
    store = Store(root)
    store.load()

    failures = []
    for uid, req in store.requirements.items():
        if req.get("deleted"):
            continue
        stored = req.get("content_hash", "")
        computed = compute_requirement_hash(req)
        if stored and stored != computed:
            failures.append(f"requirement {req.get('id', uid)}: hash mismatch")

    for uid, p in store.principles.items():
        stored = p.get("content_hash", "")
        computed = compute_principle_hash(p)
        if stored and stored != computed:
            failures.append(f"principle {p.get('id', uid)}: hash mismatch")

    for uid, t in store.tbds.items():
        stored = t.get("content_hash", "")
        computed = compute_tbd_hash(t)
        if stored and stored != computed:
            failures.append(f"tbd {t.get('id', uid)}: hash mismatch")

    if failures:
        click.echo(click.style("Hash verification FAILED:", fg="red"))
        for f in failures:
            click.echo(f"  {f}")
        sys.exit(1)
    else:
        click.echo(click.style("All hashes verified OK.", fg="green"))


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@cli.group()
def export():
    """Export requirements to various formats."""


@export.command("jsx")
@click.option("--product", default=None, help="Product ID filter.")
@click.option("--repo", default=None)
def export_jsx(product: Optional[str], repo: Optional[str]):
    """Export JSX viewer component."""
    root = Path(repo).resolve() if repo else _repo_root()
    from .store import Store
    from .exports import export_jsx as _export_jsx
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
    from .store import Store
    from .exports import export_markdown as _export_md
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
    from .store import Store
    from .exports import export_csv as _export_csv
    store = Store(root)
    store.load()
    content = _export_csv(store, product_id=product)
    out_dir = root / store.config.export.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "requirements.csv"
    out_path.write_bytes(content.encode("utf-8"))
    click.echo(f"Written: {out_path}")


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

@cli.command("import")
@click.argument("module_id")
@click.option("--product", default="", help="Product ID to lock against (default: all referencing products)")
@click.option("--repo", default=None)
def import_module(module_id: str, product: str, repo: Optional[str]):
    """Import/update a module and write the lock file."""
    root = Path(repo).resolve() if repo else _repo_root()
    from .store import Store
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


def _write_base_repo(root: Path, repo_id: str, title: str, theme: str = "dark") -> None:
    """Shared scaffold used by all init variants."""
    from .fileio import save_yaml

    for d in ("requirements", "principles", "tbds", "modules", "products", ".reqtool", "exports"):
        (root / d).mkdir(parents=True, exist_ok=True)

    config = {
        "schema_version": "1.0.0",
        "repo_id": repo_id,
        "repo_title": title,
        "git": {
            "default_branch": "main",
            "commit_name": "Requirements Tool",
            "commit_email": "reqtool@example.com",
            "sign_commits": False,
            "post_commit_hook": True,
        },
        "ui": {"default_product": None, "theme": theme},
        "export": {
            "output_dir": "exports/",
            "jsx": {"component_name": "RequirementsViewer", "include_principles": True, "include_tbds": True},
            "markdown": {"flavor": "mkdocs", "split_by": "domain"},
            "csv": {
                "delimiter": ",",
                "include_fields": [
                    "id", "title", "status", "priority", "req_type",
                    "domain", "owner", "verification_method",
                    "verification.status", "approval.status", "parentId",
                ],
            },
        },
        "validation": {
            "require_rationale_for_approved": True,
            "require_ac_for_approved": True,
            "require_owner": True,
            "warn_on_missing_test_ref": True,
            "warn_on_open_tbds_in_approved": True,
            "max_history_entries": 20,
        },
    }
    save_yaml(root / ".reqtool" / "config.yaml", config)

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("exports/\n*.pyc\n__pycache__/\n")


def _write_enums(root: Path, domains: list, nfr_keys: list = None, id_domain: dict = None) -> None:
    from .fileio import save_yaml
    save_yaml(root / ".reqtool" / "enums.yaml", {
        "domain": domains,
        "discipline": ["HW", "FW", "Sys", "Mfg", "ID", "SW"],
        "feature": [],
        "component": [],
        "team": [],
        "owner": [],
        "safety_class": [],
        "tags": [],
        "nfr_keys": nfr_keys or [
            "sampling_rate_hz", "accuracy_degc", "accuracy_rh_pct", "accuracy_hpa",
            "latency_ms", "throughput_kbps", "power_mw", "battery_life_hours",
            "startup_time_ms", "mtbf_hours",
        ],
        "id_domain": id_domain or {},
    })


def _write_product(root: Path, product_id: str, title: str) -> None:
    from .fileio import save_yaml, utcnow_iso, uuid7
    prod_dir = root / "products" / product_id
    prod_dir.mkdir(parents=True, exist_ok=True)
    now = utcnow_iso()
    save_yaml(prod_dir / "_product.yaml", {
        "schema_version": "1.0.0", "type": "product", "tool_version": "0.1.0",
        "uid": uuid7(), "id": product_id, "title": title, "version": "1.0.0",
        "content": {"description": ""},
        "modules": [], "root_requirements": [], "display_order": [],
        "content_hash": "", "created": now, "last_modified": now, "history": [],
    })


def _print_next_steps(root: Path) -> None:
    click.echo("")
    click.echo("Next steps:")
    click.echo(f"  cd {root}")
    click.echo("  git init && git add . && git commit -m 'chore: init requirements repo'")
    click.echo("  req serve")


@cli.group(invoke_without_command=True)
@click.option("--repo", default=None, help="Path for the new requirements repository root.")
@click.option("--title", default="", help="Repository title.")
@click.option("--id", "repo_id", default="", help="Repository ID (slug).")
@click.pass_context
def init(ctx, repo: Optional[str], title: str, repo_id: str):
    """Initialise a new requirements repository.

    \b
    Variants:
      req init           Blank repository (asks for ID and title)
      req init demo      Pre-filled IoT sensor product example
      req init defaults  Blank repo with a standard set of engineering principles
    """
    if ctx.invoked_subcommand is not None:
        return

    root = Path(repo).resolve() if repo else Path.cwd()
    if (root / ".reqtool" / "config.yaml").exists():
        click.echo(f"Repository already initialised at {root}", err=True)
        sys.exit(1)

    if not repo_id:
        repo_id = click.prompt("Repository ID (slug)", default=root.name)
    if not title:
        title = click.prompt("Repository title", default=repo_id.replace("-", " ").title())

    _write_base_repo(root, repo_id, title)
    _write_enums(root, domains=[])

    click.echo(click.style(f"Initialised requirements repository at {root}", fg="green"))
    click.echo(f"  Config: {root / '.reqtool' / 'config.yaml'}")
    click.echo(f"  Enums:  {root / '.reqtool' / 'enums.yaml'}")
    _print_next_steps(root)


@init.command("defaults")
@click.option("--repo", default=None)
@click.option("--title", default="", help="Repository title.")
@click.option("--id", "repo_id", default="", help="Repository ID (slug).")
def init_defaults(repo: Optional[str], title: str, repo_id: str):
    """Initialise with default principles, enums, and full type system.

    Loads from src/reqtool/defaults/ -- edit those files to change what
    gets pre-populated.

    Creates a blank repository pre-populated with:
      - ~30 principles across 8 categories (business, architecture, security,
        firmware, comms, data, process, safety)
      - Sensible starting enums for domains, disciplines, teams, and safety classes
      - Full hierarchy.yaml (agile + systems types, all workflows, DoR/DoD)
      - Agile and systems type vocabulary ready to use
    """
    from .fileio import save_yaml, load_yaml
    from .store import Store
    import shutil

    root = Path(repo).resolve() if repo else Path.cwd()
    if (root / ".reqtool" / "config.yaml").exists():
        click.echo(f"Repository already initialised at {root}", err=True)
        sys.exit(1)

    if not repo_id:
        repo_id = click.prompt("Repository ID (slug)", default=root.name)
    if not title:
        title = click.prompt("Repository title", default=repo_id.replace("-", " ").title())

    _write_base_repo(root, repo_id, title)

    # Load defaults from the package data files
    defaults_dir = Path(__file__).parent / "defaults"
    default_enums_path = defaults_dir / "enums.yaml"
    default_principles_path = defaults_dir / "principles.yaml"
    default_workflow_path = defaults_dir / "workflow.yaml"
    default_templates_path = defaults_dir / "templates.yaml"
    default_hierarchy_path = defaults_dir / "hierarchy.yaml"

    enums_to_write: dict = {}

    if not default_enums_path.exists() or not default_principles_path.exists():
        click.echo(click.style(
            f"Warning: defaults/ files not found at {defaults_dir} -- "
            "using empty enums. Run 'req init' instead or check your installation.",
            fg="yellow",
        ), err=True)
        _write_enums(root, domains=[])
    else:
        default_enums = load_yaml(default_enums_path)
        enums_to_write = {
            "domain":             default_enums.get("domain", []),
            "discipline":         default_enums.get("discipline", []),
            "feature":            default_enums.get("feature", []),
            "component":          default_enums.get("component", []),
            "team":               default_enums.get("team", []),
            "owner":              default_enums.get("owner", []),
            "safety_class":       default_enums.get("safety_class", []),
            "tags":               default_enums.get("tags", []),
            "nfr_keys":           default_enums.get("nfr_keys", []),
            "id_domain":          default_enums.get("id_domain", {}),
            # Include agile + systems estimate unit and relationship types
            "estimate_unit":      "points",
            "relationship_types": [],
        }
        save_yaml(root / ".reqtool" / "enums.yaml", enums_to_write)

    # Write workflow config into config.yaml
    if default_workflow_path.exists():
        workflow_data = load_yaml(default_workflow_path)
        config_path = root / ".reqtool" / "config.yaml"
        config_data = load_yaml(config_path) or {}
        config_data["workflow"] = workflow_data
        save_yaml(config_path, config_data)

    # Copy hierarchy.yaml so all types, workflows, and DoR/DoD are available
    if default_hierarchy_path.exists():
        shutil.copy(str(default_hierarchy_path), str(root / ".reqtool" / "hierarchy.yaml"))

    # Copy templates to project
    if default_templates_path.exists():
        shutil.copy(str(default_templates_path), str(root / ".reqtool" / "templates.yaml"))

    store = Store(root)
    store.load()

    principle_count = 0
    if default_principles_path.exists():
        principles_data = load_yaml(default_principles_path)
        if isinstance(principles_data, list):
            for p in principles_data:
                store.create_principle({
                    "id":     p.get("id", ""),
                    "title":  p.get("title", ""),
                    "domain": p.get("domain"),
                    "content": {
                        "description": p.get("description", ""),
                        "rationale":   p.get("rationale", ""),
                        "implications":p.get("implications", ""),
                        "exceptions":  p.get("exceptions", ""),
                    },
                })
                principle_count += 1

    # Group summary
    by_domain: dict[str, int] = {}
    for p in store.principles.values():
        d = p.get("domain") or "unclassified"
        by_domain[d] = by_domain.get(d, 0) + 1

    type_count = len(store.hierarchy.types)

    click.echo(click.style(f"Initialised repository with defaults at {root}", fg="green"))
    click.echo(f"  {principle_count} principles across {len(by_domain)} categories:")
    for domain, count in sorted(by_domain.items()):
        click.echo(f"    {domain:<16} {count} principles")
    click.echo(f"  Enums: {len(enums_to_write.get('domain', []))} domains, "
               f"{len(enums_to_write.get('team', []))} teams, "
               f"{len(enums_to_write.get('nfr_keys', []))} NFR keys")
    click.echo(f"  Types: {type_count} item types (agile + systems engineering)")
    click.echo(f"  Workflows: lightweight, sprint, formal, safety_formal")
    click.echo(f"  DoR/DoD: story, task, bug, spike, epic, safety, functional")
    click.echo()
    click.echo(f"  Edit defaults: {defaults_dir}/")
    _print_next_steps(root)


@init.command("demo")
@click.option("--repo", default=None)
def init_demo(repo: Optional[str]):
    """Initialise with the full IoT environmental sensor demo dataset.

    203 requirements across 4 levels (stakeholder need → system →
    subsystem → derived), 8 TBDs, and 10 principles.
    """
    from .store import Store

    root = Path(repo).resolve() if repo else Path.cwd()
    if (root / ".reqtool" / "config.yaml").exists():
        click.echo(f"Repository already initialised at {root}", err=True)
        sys.exit(1)

    _write_base_repo(root, "iot-sensor", "IoT Environmental Sensor")
    _write_enums(root,
        domains=["need","sensing","comms","power","mechanical","thermal",
                 "industrial","security","safety","compliance","ux",
                 "manufacture","identity","firmware","data","cost","system"],
        nfr_keys=["sampling_rate_hz","accuracy_degc","accuracy_rh_pct","accuracy_hpa",
                  "battery_life_months","setup_time_minutes","latency_ms",
                  "range_m","ip_rating","mtbf_hours","mass_g","battery_count"],
        id_domain={"N":"N","SR":"SR","SYS":"SYS","DR":"DR"},
    )
    # Populate demo owner and safety_class lists
    from .fileio import load_yaml, save_yaml
    enums_path = root / ".reqtool" / "enums.yaml"
    enums = load_yaml(enums_path)
    enums["owner"] = [
        "systems.lead", "firmware.lead", "hardware.lead",
        "product.management", "security.lead", "id.lead", "qa.lead",
    ]
    enums["safety_class"] = ["SIL-1","SIL-2","SIL-3","SIL-4","ASIL-A","ASIL-B","ASIL-C","ASIL-D","Cat-1","Cat-2","Cat-3"]
    enums["team"] = ["firmware","hardware","systems","security","product","id","qa","manufacture"]
    enums["tags"] = ["critical-path","psti","matter","tls","ota","nfr","battery","ui","regulatory","security"]
    enums["component"] = ["sensor","radio","power","mcu","enclosure","label","firmware","web-ui"]
    enums["discipline"] = ["FW","HW","Sys","Mfg","ID","SW","QA"]
    save_yaml(enums_path, enums)
    _write_product(root, "env-sensor-v1", "Environmental Sensor v1")

    store = Store(root)
    store.load()
    uid_map: dict = {}

    PRIORITY_MAP = {
        "security": "critical", "safety": "critical", "compliance": "critical",
    }
    TYPE_MAP = {
        "security": "security", "safety": "safety",
        "compliance": "compliance", "need": "stakeholder_need",
    }

    # 203 requirements from the IoT sensor JSX dataset
    REQS = [
        {"id":"N-001","parentId":None,"title":"Stakeholder Need",
         "text":"Provide consumers with an affordable, easy-to-install device for monitoring indoor temperature, humidity and barometric pressure that integrates with mainstream smart home ecosystems and requires no professional installation or ongoing subscription.","domain":"need",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-SEN","parentId":"N-001","title":"Environmental Measurement",
         "text":"The product shall measure indoor ambient temperature, relative humidity and barometric pressure and make readings available to the user and to connected systems.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-ECO","parentId":"N-001","title":"Smart Home Integration",
         "text":"The product shall integrate with mainstream consumer smart home platforms including Google Home, without proprietary hubs or subscriptions.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-CONN","parentId":"N-001","title":"Wireless Connectivity",
         "text":"The product shall operate wirelessly and connect to a home network without physical installation.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-UX","parentId":"N-001","title":"Consumer Usability",
         "text":"The product shall be set up and operated by a non-technical consumer without specialist tools, training or assistance.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-PWR","parentId":"N-001","title":"Untethered Operation",
         "text":"The product shall operate without a mains connection or wired data cable.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-FORM","parentId":"N-001","title":"Physical Form and Appearance",
         "text":"The product shall have a physical size, colour and finish appropriate for a consumer home and consistent with the company brand.","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-ENV","parentId":"N-001","title":"Home Environment Suitability",
         "text":"The product shall operate throughout a typical UK home including spaces subject to temperature extremes, condensation or occasional splashing.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-SEC","parentId":"N-001","title":"Consumer Cybersecurity",
         "text":"The product shall protect the consumer's home network and personal data from exploitation through the device.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-SAF","parentId":"N-001","title":"Consumer Safety",
         "text":"The product shall be safe for use in the home by the general public including children.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-REG","parentId":"N-001","title":"Regulatory Compliance",
         "text":"The product shall comply with all applicable UK legislation required for market placement.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-COST","parentId":"N-001","title":"Affordability",
         "text":"The product shall be manufacturable and sellable at a retail price accessible to mainstream consumers. [TBD-001]","domain":"cost",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-REL","parentId":"N-001","title":"Reliability and Longevity",
         "text":"The product shall operate reliably over its service life without maintenance beyond battery replacement.","domain":"system",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SR-INT","parentId":"N-001","title":"Third-Party Integration",
         "text":"The product shall support integration with third-party home automation and data logging systems. [P-MQTT]","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEN-1","parentId":"SR-SEN","title":"Temperature Measurement",
         "text":"The product shall measure ambient temperature.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEN-2","parentId":"SR-SEN","title":"Humidity Measurement",
         "text":"The product shall measure ambient relative humidity.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEN-3","parentId":"SR-SEN","title":"Pressure Measurement",
         "text":"The product shall measure ambient barometric pressure.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEN-4","parentId":"SR-SEN","title":"Sampling Rate Control",
         "text":"The rate at which readings are taken shall be user-configurable.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEN-5","parentId":"SR-SEN","title":"Measurement Accuracy Integrity",
         "text":"Sensor readings shall represent true ambient conditions and shall not be degraded by internal self-heating.","domain":"thermal",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEN-6","parentId":"SR-SEN","title":"Sensor Fault Reporting",
         "text":"The product shall detect and report measurement failures without publishing invalid or stale data.","domain":"data",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-ECO-1","parentId":"SR-ECO","title":"Matter Protocol",
         "text":"The product shall implement Matter 1.x. [P-MATTER]","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-ECO-2","parentId":"SR-ECO","title":"Google Home",
         "text":"The product shall be discoverable and fully functional in Google Home following standard Matter commissioning.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-ECO-3","parentId":"SR-ECO","title":"QR Code Commissioning",
         "text":"The product shall support Matter commissioning by QR code scan with no other steps.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-CONN-1","parentId":"SR-CONN","title":"2.4 GHz Wi-Fi",
         "text":"The product shall connect to a 2.4 GHz home Wi-Fi network.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-CONN-2","parentId":"SR-CONN","title":"Thread Mesh",
         "text":"The product shall participate in a Thread mesh network.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-CONN-3","parentId":"SR-CONN","title":"Wi-Fi Security",
         "text":"The product shall support current Wi-Fi security standards to protect the home network.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-CONN-4","parentId":"SR-CONN","title":"Indoor Range",
         "text":"The product shall maintain reliable wireless connectivity throughout a typical UK home.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-CONN-5","parentId":"SR-CONN","title":"Auto-Reconnect",
         "text":"The product shall restore all wireless connections automatically after interruption without user action.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-UX-1","parentId":"SR-UX","title":"Setup Time",
         "text":"A consumer shall complete initial setup within 5 minutes following supplied instructions, without prior technical knowledge.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-UX-2","parentId":"SR-UX","title":"Credential Entry",
         "text":"The product shall provide a mechanism for entering Wi-Fi credentials without a pre-existing network connection or separate app.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-UX-3","parentId":"SR-UX","title":"Local Config Interface",
         "text":"The product shall provide a locally accessible configuration and data interface requiring no cloud service.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-UX-4","parentId":"SR-UX","title":"Status Visibility",
         "text":"The product shall give the user visible indication of its operational state without requiring a phone or app.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-UX-5","parentId":"SR-UX","title":"User Reset",
         "text":"The user shall be able to reset the product to factory state and re-commission it without specialist tools.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-UX-6","parentId":"SR-UX","title":"Supplied Documentation",
         "text":"The product shall include sufficient documentation for a non-technical consumer to install, commission and operate it.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-PWR-1","parentId":"SR-PWR","title":"Battery Operation",
         "text":"The product shall be powered by widely available, user-replaceable consumer batteries.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-PWR-2","parentId":"SR-PWR","title":"Battery Life",
         "text":"The product shall operate for ≥ 12 months on a fresh set under reference conditions.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-PWR-3","parentId":"SR-PWR","title":"Low Battery Notification",
         "text":"The product shall notify the user when battery replacement is required before the device stops operating.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-PWR-4","parentId":"SR-PWR","title":"Tool-Free Battery Replacement",
         "text":"The user shall replace batteries without tools and without losing configuration.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-FORM-1","parentId":"SR-FORM","title":"Enclosure Size",
         "text":"The assembled product shall be compact and unobtrusive for domestic wall or shelf placement.","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-FORM-2","parentId":"SR-FORM","title":"Colour and Finish",
         "text":"The colour and surface finish shall match the company brand specification and be appropriate for a domestic interior.","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-FORM-3","parentId":"SR-FORM","title":"Aesthetic Coherence",
         "text":"All visible surfaces, labels, apertures and indicators shall present a consistent, intentional aesthetic.","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-FORM-4","parentId":"SR-FORM","title":"Mass",
         "text":"The assembled product shall not exceed a mass that makes wall mounting or shelf placement impractical.","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-ENV-1","parentId":"SR-ENV","title":"Operating Temperature",
         "text":"The product shall operate correctly across the temperature range of UK domestic environments.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-ENV-2","parentId":"SR-ENV","title":"Ingress Protection",
         "text":"The product shall be protected against dust and water splashing for domestic indoor use.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-ENV-3","parentId":"SR-ENV","title":"Wall Mounting",
         "text":"The product shall be mountable on a vertical surface without specialist fixings.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEC-1","parentId":"SR-SEC","title":"Cybersecurity Standard Compliance",
         "text":"The product shall satisfy the mandatory provisions of ETSI EN 303 645 v2.1.1 and shall comply with the UK PSTI Act 2022. PSTI mandates EN 303 645 provisions 5.1, 5.2 and 5.3 in UK law. Provisions 5.4–5.13 are recommended by EN 303 645 and shall be treated as mandatory for this product. See derived requirements DR-SEC-EN-* for clause-level detail.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEC-2","parentId":"SR-SEC","title":"Unique Per-Device Credentials",
         "text":"Each unit shall have credentials unique to that device. [P-UNIQUE]","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEC-3","parentId":"SR-SEC","title":"Protected Credential Storage",
         "text":"All credentials and key material shall be protected against extraction.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEC-4","parentId":"SR-SEC","title":"Firmware Authenticity",
         "text":"The device shall execute only firmware authenticated as originating from the manufacturer.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEC-5","parentId":"SR-SEC","title":"Secure OTA Updates",
         "text":"Firmware updates shall be authenticated and shall not leave the device inoperable if interrupted. [P-OTA]","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEC-6","parentId":"SR-SEC","title":"Encrypted Communications",
         "text":"All communications carrying credentials or personal data shall be encrypted in transit. [P-TLS]","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEC-7","parentId":"SR-SEC","title":"Security Update Support",
         "text":"The manufacturer shall provide security updates for a stated minimum support period. [TBD-005]","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SEC-8","parentId":"SR-SEC","title":"Vulnerability Disclosure",
         "text":"The manufacturer shall publish a vulnerability disclosure policy.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SAF-1","parentId":"SR-SAF","title":"Electrical Safety",
         "text":"The product shall present no risk of shock, fire or burn.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SAF-2","parentId":"SR-SAF","title":"Battery Safety",
         "text":"The product shall protect against battery reversal, short circuit and leakage hazards.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SAF-3","parentId":"SR-SAF","title":"Physical Safety",
         "text":"The product shall present no accessible sharp edges or physical hazards.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-SAF-4","parentId":"SR-SAF","title":"Child Safety",
         "text":"Accessible components shall not present a choking hazard to young children.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REG-1","parentId":"SR-REG","title":"UKCA Marking",
         "text":"The product shall satisfy conformity assessment requirements for the UKCA mark.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REG-2","parentId":"SR-REG","title":"Radio Spectrum",
         "text":"All radio transmissions shall comply with UK spectrum requirements.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REG-3","parentId":"SR-REG","title":"EMC",
         "text":"The product shall not cause harmful interference and shall be immune to reasonable interference levels.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REG-4","parentId":"SR-REG","title":"Hazardous Substances",
         "text":"The product shall not contain restricted substances above permitted thresholds.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REG-5","parentId":"SR-REG","title":"WEEE",
         "text":"The product shall comply with the UK WEEE Regulations 2013.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REG-6","parentId":"SR-REG","title":"Mandatory Labelling",
         "text":"The product label shall carry all marks and information required by UK legislation.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-COST-1","parentId":"SR-COST","title":"Unit Cost Target",
         "text":"The product shall be manufacturable at a unit cost consistent with retail price [TBD-001]. [TBD-001]","domain":"cost",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-COST-2","parentId":"SR-COST","title":"Standard Components",
         "text":"The product shall use widely available standard components to avoid sole-source supply risk.","domain":"cost",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-COST-3","parentId":"SR-COST","title":"Standard Manufacture",
         "text":"The product shall be manufacturable using standard electronics assembly and test processes at commercial volumes.","domain":"cost",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REL-1","parentId":"SR-REL","title":"MTBF",
         "text":"The product shall achieve MTBF ≥ 50,000 hours under normal indoor conditions.","domain":"system",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REL-2","parentId":"SR-REL","title":"Fault Recovery",
         "text":"The product shall recover from software faults without user intervention.","domain":"firmware",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-REL-3","parentId":"SR-REL","title":"Storage Survivability",
         "text":"The product shall survive storage and transit without damage.","domain":"system",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-INT-1","parentId":"SR-INT","title":"MQTT Interface",
         "text":"The product shall provide an MQTT interface for telemetry and control. [P-MQTT]","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"SYS-INT-2","parentId":"SR-INT","title":"Local Data Access",
         "text":"Sensor data and configuration shall be accessible via a local network interface without cloud dependency.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-T-1","parentId":"SYS-SEN-1","title":"Temperature Range",
         "text":"Temperature measurement range: -20 °C to +50 °C.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-T-2","parentId":"SYS-SEN-1","title":"Temperature Accuracy",
         "text":"Accuracy: ±0.5 °C across the full range, measured after 30 min stabilisation.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-T-3","parentId":"SYS-SEN-1","title":"Temperature Resolution",
         "text":"Reported to 0.1 °C resolution.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-T-4","parentId":"SYS-SEN-1","title":"Temperature Compensation",
         "text":"The firmware shall apply the sensor manufacturer's compensation algorithm to raw data before publishing.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-T-5","parentId":"SYS-SEN-1","title":"Temperature Cal Offset",
         "text":"User-configurable calibration offset of ±5.0 °C in 0.1 °C steps via web interface. Applied to every reading. Persists across reboots and firmware updates.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-T-6","parentId":"SYS-SEN-1","title":"Temperature Bounds",
         "text":"Compensated values outside -40 °C to +85 °C shall be treated as faults and shall not be published as valid readings.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-H-1","parentId":"SYS-SEN-2","title":"Humidity Range",
         "text":"Range: 0 %RH to 100 %RH.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-H-2","parentId":"SYS-SEN-2","title":"Humidity Accuracy",
         "text":"Accuracy: ±3 %RH over 20–80 %RH at 25 °C.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-H-3","parentId":"SYS-SEN-2","title":"Humidity Compensation",
         "text":"The firmware shall apply the manufacturer's temperature-compensated humidity algorithm using the temperature from the same sample cycle.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-H-4","parentId":"SYS-SEN-2","title":"Humidity Bounds",
         "text":"Compensated humidity outside -1 %RH to 101 %RH shall be treated as faults.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-P-1","parentId":"SYS-SEN-3","title":"Pressure Range",
         "text":"Range: 300 hPa to 1100 hPa.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-P-2","parentId":"SYS-SEN-3","title":"Pressure Accuracy",
         "text":"Accuracy: ±1 hPa at 25 °C over the full range.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-P-3","parentId":"SYS-SEN-3","title":"Pressure Compensation",
         "text":"The firmware shall apply the manufacturer's full compensation sequence including filter stages to raw pressure data.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-P-4","parentId":"SYS-SEN-3","title":"Pressure Bounds",
         "text":"Compensated pressure outside 250 hPa to 1200 hPa shall be treated as faults.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SAMP-1","parentId":"SYS-SEN-4","title":"Sample Interval",
         "text":"Configurable 1–3600 s, default 60 s. Persists across reboots and firmware updates.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SAMP-2","parentId":"SYS-SEN-4","title":"Synchronised Timestamp",
         "text":"All three readings in a sample cycle shall carry an identical timestamp in all published payloads.","domain":"sensing",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SAMP-3","parentId":"SYS-SEN-4","title":"Post-Wake Settling Delay",
         "text":"The firmware shall wait ≥ 100 ms after returning from low-power state before initiating measurements. This is a named firmware constant; thermal characterisation may increase it.","domain":"sensing",
         "disc":None,"test":None,"note":"100 ms is a floor. Actual value set by DR-THRM-2 characterisation. Must be a named constant, not a literal.",
         "status_flag":"M"},
        {"id":"DR-THRM-1","parentId":"SYS-SEN-5","title":"Thermal Separation",
         "text":"Heat-generating components shall be separated from the sensing element such that the element temperature does not exceed ambient + 0.4 °C at steady state, 25 °C ambient, full Wi-Fi operation.","domain":"thermal",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-THRM-2","parentId":"SYS-SEN-5","title":"Post-Wake Thermal Recovery",
         "text":"The firmware shall not capture readings until the sensing element stabilises to within 0.2 °C of its pre-wake value. The delay shall be characterised and set as a named constant ≥ DR-SAMP-3.","domain":"thermal",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-THRM-3","parentId":"SYS-SEN-5","title":"Enclosure Air Exchange",
         "text":"With IP45 sealing intact, assembled readings shall not differ from open-air by more than 0.3 °C or 1 %RH after 10 min equilibration.","domain":"thermal",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-THRM-4","parentId":"SYS-SEN-5","title":"Internal Airflow",
         "text":"The enclosure geometry shall not create sealed air pockets trapping heat from active components near the sensing element.","domain":"thermal",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-DATA-1","parentId":"SYS-SEN-6","title":"Fault Detection",
         "text":"The firmware shall detect failure to obtain a valid reading after 3 consecutive retries and raise a sensor fault. It shall not publish the previous reading as a current measurement.","domain":"data",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-DATA-2","parentId":"SYS-SEN-6","title":"Fault Propagation",
         "text":"A sensor fault shall appear across all active interfaces within one sample cycle: indicator → fault pattern; MQTT payload → quality='fault', null numeric fields; Matter cluster → null value; web dashboard → fault indicator.","domain":"data",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-DATA-3","parentId":"SYS-SEN-6","title":"Fault Auto-Recovery",
         "text":"The firmware shall attempt recovery every sample cycle. Normal reporting shall resume within one cycle of readings becoming valid.","domain":"data",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-DATA-4","parentId":"SYS-SEN-6","title":"Timestamp Validity Flag",
         "text":"Every published reading shall include 'time_synced': true when NTP-derived, false when using uptime since boot. [P-JSON]","domain":"data",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MAT-1","parentId":"SYS-ECO-1","title":"Temperature Cluster",
         "text":"Matter TemperatureMeasurement cluster 0x0402: MeasuredValue, MinMeasuredValue, MaxMeasuredValue — updated every sample cycle.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MAT-2","parentId":"SYS-ECO-1","title":"Humidity Cluster",
         "text":"Matter RelativeHumidityMeasurement cluster 0x0405 — updated every sample cycle.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MAT-3","parentId":"SYS-ECO-1","title":"Pressure Cluster",
         "text":"Matter PressureMeasurement cluster 0x0403 — updated every sample cycle.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MAT-4","parentId":"SYS-ECO-1","title":"PowerSource Cluster",
         "text":"Battery level via Matter PowerSource cluster — updated every sample cycle.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MAT-5","parentId":"SYS-ECO-1","title":"Null on Fault",
         "text":"When a sensor fault is active, the corresponding Matter cluster attribute shall report the Matter-defined null value, not a stale reading.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WIFI-1","parentId":"SYS-CONN-1","title":"IEEE 802.11 b/g/n",
         "text":"The product shall support IEEE 802.11 b/g/n at 2.4 GHz.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WIFI-2","parentId":"SYS-CONN-3","title":"WPA2/WPA3 Only",
         "text":"WPA2-Personal and WPA3-Personal shall be supported. WEP and open networks shall not be joinable.\\nNote (negative req): the prohibition is paired with the positive requirement above. WEP and open are called out explicitly because they are known-vulnerable modes that a consumer might inadvertently select.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WIFI-3","parentId":"SYS-CONN-4","title":"Wi-Fi Range",
         "text":"RSSI ≥ -80 dBm at 30 m through two plasterboard walls from the test AP, enclosure fully assembled.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WIFI-4","parentId":"SYS-CONN-5","title":"Wi-Fi Reconnect Backoff",
         "text":"Exponential backoff: 5 s initial, doubling, capped at 300 s. Fully automatic.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WIFI-5","parentId":"SYS-UX-2","title":"Setup Network",
         "text":"On first boot or factory reset: broadcast SSID 'Setup-[last 6 digits of serial]'; serve credential entry page at 192.168.4.1; no network password required.","domain":"comms",
         "disc":None,"test":None,"note":"SSID format and IP are fixed to remove ambiguity. The network is open because it serves only a credential entry page containing no sensor data.",
         "status_flag":"M"},
        {"id":"DR-WIFI-6","parentId":"SYS-UX-2","title":"Setup Timeout",
         "text":"Setup network closes after 10 min with no submitted credentials. Indicator shows fault pattern. Reset button reactivates setup mode.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-THR-1","parentId":"SYS-CONN-2","title":"IEEE 802.15.4 2.4 GHz",
         "text":"The product shall support IEEE 802.15.4 at 2.4 GHz, required for Thread participation.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-THR-2","parentId":"SYS-CONN-2","title":"Thread 1.3 Sleepy ED",
         "text":"Implement Thread 1.3 or later as a Sleepy End Device. Shall not operate as a Router or Border Router.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-THR-3","parentId":"SYS-CONN-4","title":"Thread Range",
         "text":"Packet loss ≤ 1% at 15 m through two plasterboard walls, fully assembled.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MQTT-1","parentId":"SYS-INT-1","title":"MQTT 3.1.1",
         "text":"Implement MQTT 3.1.1. [P-MQTT]","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MQTT-2","parentId":"SYS-INT-1","title":"TLS-Only MQTT",
         "text":"MQTT shall use TLS 1.2 minimum on port 8883. Unencrypted MQTT (port 1883) shall be disabled and shall not be user-configurable. [P-TLS]","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MQTT-3","parentId":"SYS-INT-1","title":"Telemetry Payload",
         "text":"On every sample: publish JSON to telemetry topic containing: device_id (string), firmware_version (string), timestamp_utc (ISO 8601), time_synced (boolean), temperature_c (number 1 d.p. or null), humidity_pct (number 1 d.p. or null), pressure_hpa (number 1 d.p. or null), battery_pct (integer 0–100), sensor_fault (boolean). Topic hierarchy: [TBD-007]. [P-MQTT] [P-JSON]","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MQTT-4","parentId":"SYS-INT-1","title":"Control Commands",
         "text":"Subscribe to control topic; process: set_sample_interval (int 1–3600), trigger_reading, request_status, set_friendly_name (string ≤ 32 chars). JSON acknowledgement on response topic for each command. [TBD-007]","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MQTT-5","parentId":"SYS-INT-1","title":"MQTT Reconnect Backoff",
         "text":"After broker disconnection: exponential backoff 5 s initial, doubling, capped at 300 s. Automatic.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MQTT-6","parentId":"SYS-INT-1","title":"Broker Config",
         "text":"User-configurable: hostname/IP, port (default 8883), client ID (default: device serial), username, password.","domain":"comms",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MQTT-7","parentId":"SYS-INT-1","title":"[D] MQTT 5.0 Support",
         "text":"The product may additionally support MQTT 5.0 for enhanced diagnostic messaging. MQTT 3.1.1 (DR-MQTT-1) remains the mandatory baseline. This is a desired enhancement and is not a gate criterion.","domain":"comms",
         "disc":None,"test":None,"note":"DESIRED: implement only if no cost or schedule impact. Does not gate product conformance.",
         "status_flag":"D"},
        {"id":"DR-WEB-1","parentId":"SYS-UX-3","title":"HTTPS Only",
         "text":"Served at https://[device-ip]/ port 443. HTTP port 80 shall redirect to HTTPS. Fully functional without internet. [P-REST] [P-TLS]","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WEB-2","parentId":"SYS-UX-3","title":"Authentication",
         "text":"All pages and endpoints require authentication. Sessions expire after 30 min inactivity. Maximum 3 simultaneous sessions.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WEB-3","parentId":"SYS-UX-3","title":"REST JSON API",
         "text":"REST API with JSON bodies: GET/PUT config, GET readings, GET status, GET firmware version, POST OTA trigger. [P-REST] [P-JSON]","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WEB-4","parentId":"SYS-UX-3","title":"Configuration Scope",
         "text":"Configurable: Wi-Fi SSID/password, MQTT hostname/port/client ID/username/password, sample interval, temperature offset (±5.0 °C, 0.1 °C), humidity offset (±5.0 %RH, 0.1 %RH), friendly name (≤ 32 chars), NTP hostname. Take effect ≤ 5 s after save except Wi-Fi (next reboot).","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WEB-5","parentId":"SYS-UX-3","title":"Live Dashboard",
         "text":"Dashboard updates every sample cycle without page refresh. Readings appear ≤ 2 s after sample event.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WEB-6","parentId":"SYS-UX-3","title":"Status Display",
         "text":"Dashboard shows: per-sensor fault indicators; connectivity (Wi-Fi/MQTT/Matter separately); low battery (≤ 15%); last reading timestamp; device IP; firmware version.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-WEB-7","parentId":"SYS-UX-3","title":"[D] Reading History",
         "text":"The web dashboard may display a 24-hour history graph of temperature, humidity and pressure. This is a desired enhancement; it does not gate product conformance.","domain":"ux",
         "disc":None,"test":None,"note":"DESIRED: implement only if storage budget and schedule permit. Not a mandatory capability.",
         "status_flag":"D"},
        {"id":"DR-IND-1","parentId":"SYS-UX-4","title":"RGB LED",
         "text":"One RGB LED through front face. Visible at 3 m in ≤ 500 lux ambient. Colour spec: [TBD-008].","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-IND-2","parentId":"SYS-UX-4","title":"Setup: Blue 1 Hz",
         "text":"Setup network active → blue 1 Hz (500 ms on, 500 ms off).","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-IND-3","parentId":"SYS-UX-4","title":"Connecting: Yellow 2 Hz",
         "text":"Connecting to Wi-Fi or Matter commissioning → yellow 2 Hz (250 ms on, 250 ms off).","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-IND-4","parentId":"SYS-UX-4","title":"Normal: Green 200 ms",
         "text":"Normal operation → 200 ms green pulse per sample event, then off.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-IND-5","parentId":"SYS-UX-4","title":"Fault: Red 0.5 Hz",
         "text":"Sensor fault or connectivity failure persisting > 10 min → red 0.5 Hz (1000 ms on, 1000 ms off). Overrides DR-IND-4.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-IND-6","parentId":"SYS-UX-4","title":"Low Battery: Red Double-Blink",
         "text":"Battery ≤ 15% → red double-blink (200/200/200/1400 ms) every 30 s. Fault pattern (DR-IND-5) takes priority.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-IND-7","parentId":"SYS-UX-4","title":"LED States Documented",
         "text":"All patterns DR-IND-2 through DR-IND-6 shall be documented in the QSG and web interface help page.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-RST-1","parentId":"SYS-UX-5","title":"Recessed Reset",
         "text":"Recessed pushbutton accessible only with battery cover removed; requires 1.5–3 mm diameter implement to activate.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-RST-2","parentId":"SYS-UX-5","title":"Short Press: Reboot",
         "text":"Press 1–4 s: clean reboot, all config retained. LED emits two yellow flashes before reboot.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-RST-3","parentId":"SYS-UX-5","title":"Long Press: Factory Reset",
         "text":"Press ≥ 5 s: LED blinks red 5 Hz for 3 s (cancel window — release to abort). On completion: erase all user config/credentials; reboot into setup mode.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-RST-4","parentId":"SYS-UX-5","title":"Reset Scope",
         "text":"Factory reset erases: Wi-Fi SSID/password, MQTT settings, web password, temperature/humidity offsets, friendly name, NTP override, Matter fabric bindings, active sessions. Firmware version is not altered.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FORM-1","parentId":"SYS-FORM-1","title":"Max Dimensions 80×80×35 mm",
         "text":"Assembled product including wall-mount feature: max 80 mm (H) × 80 mm (W) × 35 mm (D). [TBD-002]","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FORM-2","parentId":"SYS-FORM-4","title":"Max Mass 200 g",
         "text":"Assembled including two AA batteries: ≤ 200 g. [TBD-002]","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FORM-3","parentId":"SYS-FORM-2","title":"Colour: RAL 9016 Matt White",
         "text":"Primary colour: matt white to RAL 9016. Production samples: ΔE ≤ 2.0 vs RAL 9016 standard. [TBD-002]","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FORM-4","parentId":"SYS-FORM-2","title":"Finish: 5–15 GU Matt",
         "text":"All external surfaces: matt finish, 5–15 GU at 60°. [TBD-002]","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FORM-5","parentId":"SYS-FORM-3","title":"Cover Snap-Fit 10–25 N",
         "text":"Battery cover retained by snap-fit: 10–25 N removal force. No screws or adhesive.","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FORM-6","parentId":"SYS-FORM-3","title":"No Visible Fasteners",
         "text":"No screws or fasteners visible on front or side faces in assembled state.","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FORM-7","parentId":"SYS-FORM-3","title":"LED Aperture 4.0±0.5 mm",
         "text":"Circular aperture or lens in front face: 4.0 mm ± 0.5 mm diameter. Shall not distort LED colour. [TBD-008]","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FORM-8","parentId":"SYS-FORM-3","title":"Rear Label Area ≥ 40×25 mm",
         "text":"Rear face: permanent label area ≥ 40 mm × 25 mm carrying serial number (human-readable + Code 128 barcode), Matter QR + 11-digit pairing code, regulatory marks, '2 × LR6 (AA)', '-20 °C to +50 °C', 'IP45', VDP URL, manufacturer name and address.","domain":"industrial",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-PWR-1","parentId":"SYS-PWR-1","title":"LR6 (AA) IEC 60086-1",
         "text":"Two LR6 (AA) cells in series; compartment accepts any IEC 60086-1 conforming cells.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-PWR-2","parentId":"SYS-PWR-1","title":"Voltage Range 2.0–3.6 V",
         "text":"All functions shall operate from 2.0 V (end-of-life alkaline) to 3.6 V (fresh lithium AA) across -20 °C to +50 °C.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-PWR-3","parentId":"SYS-PWR-3","title":"Battery Level 0–100%",
         "text":"Capacity estimated as 0–100% and published with every reading via MQTT, Matter PowerSource and web dashboard. Updated every sample cycle.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-PWR-4","parentId":"SYS-PWR-3","title":"Low Battery Threshold",
         "text":"Low battery raised at ≤ 15%; clears above 20%. Reported across all interfaces and indicator DR-IND-6.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-PWR-5","parentId":"SYS-PWR-4","title":"Config Retained on Swap",
         "text":"Removing and reinserting batteries within 60 s shall not cause loss of any stored configuration.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-PWR-6","parentId":"SYS-PWR-2","title":"Avg Current ≤ 150 µA",
         "text":"Average current over a complete 60 s sample cycle at reference conditions (Wi-Fi connected, no MQTT, 20 °C) shall not exceed 150 µA.","domain":"power",
         "disc":None,"test":None,"note":"150 µA average over 60 s is consistent with ≥ 12 months on 2 × AA alkaline at 2500 mAh.",
         "status_flag":"M"},
        {"id":"DR-PWR-7","parentId":"SYS-PWR-2","title":"Supply ≥ 2.0 V at -20 °C",
         "text":"Supply voltage shall not fall below 2.0 V during peak transmit at -20 °C with LR6 alkaline cells.","domain":"power",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ENC-1","parentId":"SYS-ENV-1","title":"Operating Temp -20 to +50 °C",
         "text":"Fully functional from -20 °C to +50 °C.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ENC-1a","parentId":"SYS-ENV-1","title":"Component Temp Rating",
         "text":"All components rated for ≤ -20 °C lower end and ≥ +85 °C upper end.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ENC-1b","parentId":"SYS-ENV-1","title":"Material Temp Range",
         "text":"All enclosure materials, gaskets and adhesives retain properties across -20 °C to +50 °C.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ENC-2","parentId":"SYS-ENV-2","title":"IP45 per IEC 60529",
         "text":"Achieve at least IP45 per IEC 60529. IP4X (Clause 13.4): dust test — 1 kg talc, 8-hour agitation, no harmful deposit. IPX5 (Clause 14.2.5): water jet test — 12.5 l/min, 6.3 mm nozzle, 3 m distance, 15 min all directions. Rating maintained after 10 thermal cycles.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ENC-3","parentId":"SYS-ENV-3","title":"Keyhole Wall Mount",
         "text":"Rear face keyhole slot for 4.0 mm pan-head screw (max head Ø 8.5 mm). Mounted on one screw: withstands 3× product mass downward load.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ENC-4","parentId":"SYS-REL-3","title":"Storage -30 to +60 °C",
         "text":"With batteries removed: survives -30 °C to +60 °C storage without damage or IP45 loss.","domain":"mechanical",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.1","parentId":"SYS-SEC-1","title":"EN 303 645 §5.1: No Universal Default Passwords [PSTI]",
         "text":"EN 303 645 v2.1.1 Provision 5.1 (Mandatory in standard; also mandated by PSTI Act 2022 Schedule 1 §1). All device passwords shall be unique per device and shall not be resettable to a universal factory default. If no password is required for a network interface, the interface shall not be enabled by default unless there is documented justification in a security analysis. [P-UNIQUE]","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.2","parentId":"SYS-SEC-1","title":"EN 303 645 §5.2: Vulnerability Disclosure Policy [PSTI]",
         "text":"EN 303 645 v2.1.1 Provision 5.2 (Mandatory; also mandated by PSTI Act 2022 Schedule 1 §2). A public vulnerability disclosure policy (VDP) shall be published and kept up to date. The VDP shall include: a point of contact for security researchers, a commitment to timely acknowledgement of valid vulnerability reports, and information on the expected timeline to resolution. The VDP URL shall be printed on the product label.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.3","parentId":"SYS-SEC-1","title":"EN 303 645 §5.3: Software Updates [PSTI]",
         "text":"EN 303 645 v2.1.1 Provision 5.3 (Mandatory; also mandated by PSTI Act 2022 Schedule 1 §3). The product shall support software updates. [P-OTA] The minimum support period shall be stated on the product packaging and in accompanying documentation. [TBD-005] Updates shall be timely (critical security patches within 90 days of a verified vulnerability being reported). The product shall notify the user when a software update is available. Where possible, updates shall be verified before installation (see DR-SEC-6).","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.4","parentId":"SYS-SEC-1","title":"EN 303 645 §5.4: Secure Storage of Credentials",
         "text":"EN 303 645 v2.1.1 Provision 5.4 (Recommended in standard — treated as mandatory for this product per SYS-SEC-1). Sensitive security parameters in persistent storage shall be stored securely. Hard-coded credentials in device software are not acceptable. Cryptographic keys shall not be stored in plaintext.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.5","parentId":"SYS-SEC-1","title":"EN 303 645 §5.5: Communicate Securely",
         "text":"EN 303 645 v2.1.1 Provision 5.5 (Recommended — mandatory per SYS-SEC-1). The device shall use best practice cryptography for all communication. [P-TLS] All cryptographic primitives shall be current and appropriate for the use case. The device shall not use deprecated protocols (TLS 1.0, TLS 1.1, SSLv3) or deprecated cipher suites (RC4, 3DES, NULL cipher).","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.6","parentId":"SYS-SEC-1","title":"EN 303 645 §5.6: Minimise Exposed Attack Surfaces",
         "text":"EN 303 645 v2.1.1 Provision 5.6 (Recommended — mandatory per SYS-SEC-1). Network interfaces, physical interfaces and services not required for intended operation shall be disabled. All ports, services and device capabilities shall be documented. Unused physical debug interfaces shall be disabled before leaving the production line (see DR-MFG-3).","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.7","parentId":"SYS-SEC-1","title":"EN 303 645 §5.7: Software Integrity",
         "text":"EN 303 645 v2.1.1 Provision 5.7 (Recommended — mandatory per SYS-SEC-1). The device shall verify the integrity of software using secure boot (see DR-SEC-5). Where the device detects unauthorised changes to software, it shall alert the user and shall not permit further use of compromised software.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.8","parentId":"SYS-SEC-1","title":"EN 303 645 §5.8: Personal Data Security",
         "text":"EN 303 645 v2.1.1 Provision 5.8 (Recommended — mandatory per SYS-SEC-1). All personal data communicated off-device shall be encrypted in transit. [P-TLS] Personal data stored on the device (Wi-Fi credentials, MQTT credentials, device name) shall be protected using appropriate mechanisms. The privacy notice shall explain what personal data is processed.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.9","parentId":"SYS-SEC-1","title":"EN 303 645 §5.9: Resilience to Outages",
         "text":"EN 303 645 v2.1.1 Provision 5.9 (Recommended — mandatory per SYS-SEC-1). The device shall remain operable in a degraded but functional state during a network outage. Local sensing and web interface shall remain functional when cloud connectivity or MQTT broker is unavailable. The device shall not become bricked or permanently unrecoverable due to loss of a remote service.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.10","parentId":"SYS-SEC-1","title":"EN 303 645 §5.10: Examine System Telemetry",
         "text":"EN 303 645 v2.1.1 Provision 5.10 (Recommended — mandatory per SYS-SEC-1). If system telemetry data is collected from devices, it shall be examined for security anomalies. This is a platform-level obligation: the company's IoT platform shall log and examine device telemetry for anomalous patterns. Device-side requirement: the device shall publish its firmware version and a device health status on every MQTT connection event to enable platform-side monitoring.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.11","parentId":"SYS-SEC-1","title":"EN 303 645 §5.11: User Data Deletion",
         "text":"EN 303 645 v2.1.1 Provision 5.11 (Recommended — mandatory per SYS-SEC-1). Users shall be provided with the ability to delete all personal data from the device. Factory reset (DR-RST-3, DR-RST-4) shall erase all user-provided data. The QSG shall document the factory reset procedure and state that it erases all personal data.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.12","parentId":"SYS-SEC-1","title":"EN 303 645 §5.12: Easy Installation",
         "text":"EN 303 645 v2.1.1 Provision 5.12 (Recommended — mandatory per SYS-SEC-1). Installation and maintenance of devices shall be easy and shall not require the user to make security-critical decisions that they are not equipped to make. The provisioning flow shall configure secure defaults automatically. Users shall not be asked to choose encryption protocols or key lengths.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-EN-5.13","parentId":"SYS-SEC-1","title":"EN 303 645 §5.13: Validate Input Data",
         "text":"EN 303 645 v2.1.1 Provision 5.13 (Recommended — mandatory per SYS-SEC-1). All user-provided input data, including data received via network interfaces, shall be validated. Inputs exceeding defined limits shall be rejected with an appropriate error. No input shall cause the device to crash, execute unintended code, or expose memory contents.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-4","parentId":"SYS-SEC-3","title":"Hardware Key Storage",
         "text":"Key material stored in write-protected hardware storage, locked and unreadable before unit leaves production. Not accessible via any runtime software interface.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-5","parentId":"SYS-SEC-4","title":"Firmware Signature at Boot",
         "text":"Verify firmware digital signature before execution. Failure halts execution and activates fault LED. Verification key in hardware storage (DR-SEC-4).","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-6","parentId":"SYS-SEC-5","title":"Authenticated OTA",
         "text":"Update packages verified by digital signature before installation. Failing packages rejected; device continues running current firmware.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-7","parentId":"SYS-SEC-5","title":"Interruption-Safe Update",
         "text":"Interrupting an update at any stage shall leave the device booting its previous firmware. Failure logged.","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SEC-8","parentId":"SYS-SEC-5","title":"Downgrade Prevention",
         "text":"Reject any update package with a version lower than the installed version. [P-SEMVER]","domain":"security",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SAF-1","parentId":"SYS-SAF-1","title":"BS EN 62368-1:2020",
         "text":"Comply with BS EN 62368-1:2020. Mandatory clauses: §5 (Energy source classification), §6 (Safeguard requirements), §8 (Construction and materials), §9 (Battery systems). Test report from accredited test house required before market placement.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SAF-2","parentId":"SYS-SAF-2","title":"Battery Reversal",
         "text":"Reversed batteries: no component damage, no fire/burn/shock hazard. Device non-functional but recovers when polarity corrected.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SAF-3","parentId":"SYS-SAF-2","title":"Short Circuit Protection",
         "text":"Battery terminal short circuit limited by protection circuitry: no fire/burn/shock. Resettable without servicing.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-SAF-4","parentId":"SYS-SAF-3","title":"Edge Radii ≥ 0.5 mm",
         "text":"All accessible external edges and corners: minimum radius 0.5 mm.","domain":"safety",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-REG-1","parentId":"SYS-REG-1","title":"UK Declaration of Conformity",
         "text":"UK DoC against: Radio Equipment Regulations 2017 (SI 2017/1206) — Essential requirements: §3(1)(a) safety, §3(1)(b) EMC, §3(2) radio spectrum; Electromagnetic Compatibility Regulations 2016; BS EN 62368-1. DoC completed and retained before first market placement.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-REG-2","parentId":"SYS-REG-2","title":"Radio: ETSI EN 300 328 + EN 303 131",
         "text":"2.4 GHz Wi-Fi: ETSI EN 300 328 v2.2.2, mandatory clauses: §4 (Technical requirements), §4.3 (Operational modes), §4.3.1.4 (Maximum output power ≤ 20 dBm EIRP), §4.3.2 (Receiver blocking). 802.15.4: ETSI EN 303 131 v2.1.1, mandatory clauses: §4 (Technical requirements). Test reports from UKAS-accredited test house required.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-REG-3","parentId":"SYS-REG-3","title":"Emissions: BS EN 55032:2015+A1:2020 Class B",
         "text":"Radiated and conducted emissions: BS EN 55032:2015+A1:2020. Mandatory limits: Table 4 (Class B radiated, 30–1000 MHz), Table 1 (Class B conducted, 0.15–30 MHz). Optional: CISPR 32 Ed.3 (equivalent, acceptable as alternative). All limits to Class B residential.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-REG-4","parentId":"SYS-REG-3","title":"Immunity: BS EN 55035:2017+A11:2020",
         "text":"Immunity: BS EN 55035:2017+A11:2020. Mandatory test cases (Class B): ESD per IEC 61000-4-2 (±4 kV contact, ±8 kV air), Radiated RF per IEC 61000-4-3 (3 V/m, 80–2700 MHz), EFT/burst per IEC 61000-4-4 (±1 kV), Surge per IEC 61000-4-5 (±0.5 kV), Conducted RF per IEC 61000-4-6 (3 V, 0.15–80 MHz). Note: battery-powered device — mains surge tests (IEC 61000-4-5) may not apply; confirm with test house.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-REG-5","parentId":"SYS-REG-4","title":"UK RoHS SI 2012/3032",
         "text":"UK RoHS Regulations 2012 (SI 2012/3032). Restricted substances and limits: Lead ≤ 0.1%, Mercury ≤ 0.1%, Cadmium ≤ 0.01%, Hexavalent chromium ≤ 0.1%, PBB ≤ 0.1%, PBDE ≤ 0.1%, DEHP ≤ 0.1%, BBP ≤ 0.1%, DBP ≤ 0.1%, DIBP ≤ 0.1% — all by maximum weight of homogeneous material. RoHS compliance declarations required for every BOM line item.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-REG-6","parentId":"SYS-REG-5","title":"WEEE Registration",
         "text":"Manufacturer registered as UK WEEE producer (WEEE Regulations 2013, SI 2013/3113) before market placement. Producer registration number held on file. Crossed-out wheelie bin symbol on product label.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-REG-7","parentId":"SYS-REG-6","title":"Label Content",
         "text":"Label shall carry: UKCA mark, WEEE symbol, '2 × LR6 (AA)', '-20 °C to +50 °C', 'IP45', VDP URL, manufacturer name and address. Required by SI 2017/1206 Schedule 2 (radio marking) and SI 2012/3032 (RoHS).","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-REG-8","parentId":"SYS-REG-6","title":"Matter Commissioning Label",
         "text":"Matter onboarding QR code and 11-digit manual pairing code in ≥ 8 pt font.","domain":"compliance",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ID-1","parentId":"SYS-SEC-2","title":"Unique Serial Number",
         "text":"Globally unique serial per unit at manufacture. Format: [TBD-007]. Stored in hardware write-protected storage. Printed as human-readable text and Code 128 barcode on rear label. [P-PKI]","domain":"identity",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ID-2","parentId":"SYS-SEC-2","title":"X.509 Device Certificate",
         "text":"X.509v3 device certificate signed by company intermediate CA; stored in hardware-protected storage; CN = serial number. [P-PKI] [TBD-004]","domain":"identity",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-ID-3","parentId":"SYS-SEC-2","title":"Matter DAC",
         "text":"Matter Device Attestation Certificate per Matter specification. [TBD-004]","domain":"identity",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-TIME-1","parentId":"SR-INT","title":"NTP Sync ≤ 60 s",
         "text":"Sync with pool.ntp.org (default, user-overridable) within 60 s of Wi-Fi connection; re-sync every 24 h. [P-NTP]","domain":"firmware",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-TIME-2","parentId":"SR-INT","title":"Sample Interval Accuracy ±1%",
         "text":"Configured intervals maintained ±1% across low-power periods. At 60 s: each cycle 59.4–60.6 s.","domain":"firmware",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MFG-1","parentId":"SYS-COST-3","title":"PCB Test Points",
         "text":"Labelled test points accessible by bed-of-nails for: supply voltage, ground, sensor signal buses, serial debug interface, programming interface.","domain":"manufacture",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MFG-2","parentId":"SYS-COST-3","title":"End-of-Line Test",
         "text":"Every unit passes automated EoL test: temperature ±2 °C of chamber reference; Wi-Fi scan ≥ 1 AP; all LED colours verified; reset button continuity; battery voltage within 10% of nominal. Pass/fail and timestamp logged per unit. Target reject rate ≤ 0.5%.","domain":"manufacture",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-MFG-3","parentId":"SYS-COST-3","title":"Programming Interface Disabled",
         "text":"Serial programming interface permanently disabled — not password-protected — before unit leaves production line.","domain":"manufacture",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FW-1","parentId":"SYS-REL-2","title":"Watchdog 30 s",
         "text":"Hardware watchdog active at all times; 30 s timeout; all tasks participate. Missed feed → system reset; reset reason logged.","domain":"firmware",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FW-2","parentId":"SYS-REL-2","title":"Crash Logging",
         "text":"On unexpected reset: log reset reason, timestamp, firmware version, register/stack context to persistent storage. Retain 10 most recent entries. Accessible via web diagnostic page.","domain":"firmware",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FW-3","parentId":"SYS-REL-2","title":"Config Persistence",
         "text":"All user configuration survives: power loss, clean reboot, firmware update. Factory reset is the only erasure mechanism.","domain":"firmware",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FW-4","parentId":"SYS-REL-2","title":"Concurrent Non-Interference",
         "text":"Simultaneous sensor sampling, all wireless interfaces and web interface shall not cause any function to miss timing by > 10% or exceed specified response latency.","domain":"firmware",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FW-5","parentId":"SYS-REL-2","title":"Version Reporting",
         "text":"Firmware version (MAJOR.MINOR.PATCH per [P-SEMVER]) accessible via web interface, MQTT status topic and Matter Software Diagnostics cluster.","domain":"firmware",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-FW-6","parentId":"SYS-REL-2","title":"[D] Local Reading Buffer",
         "text":"The firmware may buffer up to 24 hours of readings in persistent storage for delivery when connectivity is restored. This is a desired enhancement; it does not gate product conformance.","domain":"firmware",
         "disc":None,"test":None,"note":"DESIRED: implement only if storage budget permits. Not a mandatory capability.",
         "status_flag":"D"},
        {"id":"DR-PKG-1","parentId":"SYS-UX-6","title":"Quick Start Guide",
         "text":"Printed QSG in box: battery installation, LED state guide, Wi-Fi provisioning, Matter QR commissioning, reset procedure, VDP URL. English. [TBD-003] Legible at 400 mm.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-PKG-2","parentId":"SYS-UX-6","title":"Box Contents",
         "text":"Retail box: 1× sensor unit, 1× Quick Start Guide. Batteries not included. [TBD-006]","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
        {"id":"DR-PKG-3","parentId":"SYS-UX-6","title":"Drop Survivability 1.0 m",
         "text":"Packaged product survives 1.0 m drop onto concrete in each of 6 face orientations: no product damage, IP45 rating maintained.","domain":"ux",
         "disc":None,"test":None,"note":None,
         "status_flag":"M"},
    ]

    for r in REQS:
        parent_uid = uid_map.get(r["parentId"])
        domain = r["domain"] or "system"
        desc = r["text"] or r["title"]
        test = r.get("test") or ""
        note = r.get("note") or ""
        ext = f"Test method: {test}" if test else ("")
        if note: ext = (ext + "\n\nNote: " + note).strip()
        priority = PRIORITY_MAP.get(domain, "medium")
        if r.get("status_flag") == "D": priority = "low"
        req_type = TYPE_MAP.get(domain, "functional")
        artefact = store.create_requirement({
            "id": r["id"], "title": r["title"], "parentId": parent_uid,
            "content": {"description": desc, "rationale": "", "extended_description": ext},
            "domain": domain,
            "priority": priority,
            "req_type": req_type,
        })
        uid_map[r["id"]] = artefact["uid"]

    TBDS = [
        {"id":"TBD-001","owner":"Product Management","needed":"Pre-PDR",
         "text":"Target retail price point and unit cost target at volume.","impact":"Gates all BOM cost decisions."},
        {"id":"TBD-002","owner":"Industrial Design","needed":"Pre-PDR",
         "text":"Final ID sign-off: exact dimensions within 80×80×35 mm envelope, colour confirmation, finish confirmation, battery cover mechanism.","impact":"Gates enclosure tooling, label artwork and all dimensional requirements."},
        {"id":"TBD-003","owner":"Product Management / Legal","needed":"Pre-PDR",
         "text":"Market language scope: English-only at launch or multi-language?","impact":"Affects packaging, labelling and web interface scope."},
        {"id":"TBD-004","owner":"Product Security","needed":"Pre-alpha FW",
         "text":"Company PKI readiness: root CA, intermediate CA, DAC signing process.","impact":"Blocks device cert provisioning and Matter DAC production flow."},
        {"id":"TBD-005","owner":"Product Management","needed":"Pre-PDR",
         "text":"Minimum security update support period: 3 years (PSTI minimum) or longer?","impact":"Affects long-term FW maintenance resource planning."},
        {"id":"TBD-006","owner":"Product Management / Brand","needed":"Pre-detailed-design",
         "text":"Retail packaging: batteries included or sold separately?","impact":"Affects shelf-life requirements, packaging design and retail cost."},
        {"id":"TBD-007","owner":"Systems Engineering","needed":"Pre-alpha FW",
         "text":"MQTT topic hierarchy, JSON payload schema and serial number format for this product line.","impact":"Blocks MQTT topic schema design and integration testing."},
        {"id":"TBD-008","owner":"Industrial Design / Reg","needed":"Pre-detailed-design",
         "text":"LED indicator exact dominant wavelengths or part references, confirmed against brand and accessibility guidelines.","impact":"Affects lightpipe / lens design and PCB LED placement."},
    ]
    for t in TBDS:
        store.create_tbd({
            "id": t["id"], "title": t["text"][:60],
            "content": {"description": t["text"], "impact": t["impact"],
                        "resolution_criteria": f'Decision required by {t["needed"]}.',
                        "resolution": None},
            "status": "open", "priority": "high", "owner": t["owner"],
        })

    PRINCIPLES = [
        {"id":"P-MQTT","title":"MQTT 3.1.1 as Standard IoT Messaging",
         "text":"All IoT products shall use MQTT 3.1.1. Alternative protocols require an ADR.","rationale":"Consistent protocol across the fleet simplifies platform integration and support."},
        {"id":"P-JSON","title":"JSON as Standard Payload Format",
         "text":"All IoT message payloads shall be JSON. Binary or proprietary formats require an ADR.","rationale":"JSON is human-readable and requires no schema negotiation for basic integration."},
        {"id":"P-TLS","title":"TLS 1.2 Minimum for Encrypted Transport",
         "text":"All communications carrying credentials or user data shall use TLS 1.2 minimum. TLS 1.0 and 1.1 are prohibited. Plaintext equivalents shall be disabled by default.","rationale":"TLS 1.0/1.1 are deprecated. TLS 1.2 is the minimum acceptable standard company-wide."},
        {"id":"P-SEMVER","title":"Semantic Versioning for Firmware",
         "text":"All firmware shall use MAJOR.MINOR.PATCH semantic versioning, embedded in the build and accessible at runtime.","rationale":"Consistent versioning enables automated compatibility checks and support triage."},
        {"id":"P-REST","title":"REST for Local Device APIs",
         "text":"Local device APIs shall use RESTful HTTPS with JSON bodies.","rationale":"REST over HTTPS is universally accessible without specialist libraries."},
        {"id":"P-NTP","title":"NTP for Device Timekeeping",
         "text":"All networked devices shall synchronise via NTP. Default: pool.ntp.org. User-configurable override required.","rationale":"Consistent timestamps across the fleet are required for log correlation and audit."},
        {"id":"P-PKI","title":"Company PKI for Device Identity",
         "text":"All devices shall carry an X.509 certificate signed by the company root CA at manufacture. Self-signed certificates are not permitted in production.","rationale":"Company PKI enables fleet-wide certificate management and revocation."},
        {"id":"P-MATTER","title":"Matter as Standard Smart Home Protocol",
         "text":"All consumer smart home products shall implement Matter. Proprietary protocols require an ADR.","rationale":"Matter is the industry-standard interoperability protocol."},
        {"id":"P-OTA","title":"OTA Firmware Update Mandatory",
         "text":"All networked products shall support OTA firmware updates. Products without OTA require an ADR and Product Security sign-off.","rationale":"OTA is required to deliver security patches within the PSTI minimum support period."},
        {"id":"P-UNIQUE","title":"Unique Per-Device Credentials",
         "text":"No credential shall be identical across more than one unit. Universal default credentials are prohibited.","rationale":"Universal defaults are prohibited by UK PSTI Act 2022 and are the most common IoT vulnerability class."},
    ]
    for p in PRINCIPLES:
        store.create_principle({
            "id": p["id"], "title": p["title"],
            "content": {"description": p["text"], "rationale": p["rationale"],
                        "implications": "", "exceptions": ""},
        })

    r_count = len(store.requirements)
    t_count = len(store.tbds)
    p_count = len(store.principles)

    # -----------------------------------------------------------------------
    # Add agile items (epics → stories/tasks) linked to systems requirements
    # -----------------------------------------------------------------------
    import shutil

    # Copy hierarchy.yaml so agile types are recognised
    default_hierarchy = Path(__file__).parent / "defaults" / "hierarchy.yaml"
    if default_hierarchy.exists():
        shutil.copy(str(default_hierarchy), str(root / ".reqtool" / "hierarchy.yaml"))
        store._load_hierarchy()  # reload so prefixes are available

    # Update enums with agile types
    enums_path = root / ".reqtool" / "enums.yaml"
    from .fileio import load_yaml, save_yaml
    enums = load_yaml(enums_path)
    enums["estimate_unit"] = "points"
    enums["id_domain"] = {**enums.get("id_domain", {}),
                          "TH": "theme", "EP": "epic", "FT": "feature",
                          "US": "story", "TK": "task", "BG": "bug"}
    save_yaml(enums_path, enums)
    store._load_enums()

    def req(id_):
        """Look up uid by id."""
        for v in store.requirements.values():
            if v.get("id") == id_:
                return v["uid"]
        return None

    # Theme
    th = store.create_requirement({"id": "TH-001", "title": "Consumer IoT Sensor Platform",
        "req_type": "theme", "status": "active",
        "content": {"description": "Deliver a production-ready environmental sensor device on Matter/Wi-Fi with a supporting cloud and app ecosystem.", "rationale": ""}})

    # Epics
    ep_fw = store.create_requirement({"id": "EP-001", "title": "Sensor Firmware v1.0",
        "req_type": "epic", "parentId": th["uid"], "status": "in_progress", "estimate": 40,
        "content": {"description": "All firmware required for initial production firmware release.", "rationale": ""}})
    ep_cloud = store.create_requirement({"id": "EP-002", "title": "Cloud Integration",
        "req_type": "epic", "parentId": th["uid"], "status": "backlog", "estimate": 24,
        "content": {"description": "MQTT ingestion, time-series storage, and device management API.", "rationale": ""}})
    ep_app = store.create_requirement({"id": "EP-003", "title": "Mobile / Web Dashboard",
        "req_type": "epic", "parentId": th["uid"], "status": "backlog", "estimate": 32,
        "content": {"description": "Real-time dashboard showing sensor readings with history and alerts.", "rationale": ""}})

    # Stories and tasks -- firmware epic
    us_boot = store.create_requirement({"id": "US-001", "title": "Sensor boots and reads all three sensors within 5 s",
        "req_type": "story", "parentId": ep_fw["uid"], "status": "done", "estimate": 5,
        "assignee": "firmware.lead", "iteration": "Sprint-1",
        "content": {"description": "As a device, I boot, initialise BME280, and publish first readings within 5 s of power-on.", "rationale": ""},
        "relationships": [{"type": "satisfies", "target": {"uid": req("DR-BME-1") or req("SYS-SEN-1") or ""}}]})
    us_ota = store.create_requirement({"id": "US-002", "title": "OTA firmware update over Wi-Fi",
        "req_type": "story", "parentId": ep_fw["uid"], "status": "in_progress", "estimate": 8,
        "assignee": "firmware.lead", "iteration": "Sprint-2",
        "content": {"description": "As a device owner, I receive and apply a signed firmware update over Wi-Fi without physical access.", "rationale": ""},
        "relationships": [{"type": "satisfies", "target": {"uid": req("SR-OTA-1") or req("SYS-COMMS-1") or ""}}]})
    us_matter = store.create_requirement({"id": "US-003", "title": "Device pairs with Apple Home and Google Home via Matter",
        "req_type": "story", "parentId": ep_fw["uid"], "status": "backlog", "estimate": 13,
        "assignee": "firmware.lead", "iteration": "Sprint-3",
        "content": {"description": "As a user, I commission the device via QR code and it appears in my chosen smart home app.", "rationale": ""}})

    tk_bme = store.create_requirement({"id": "TK-001", "title": "Integrate BME280 driver with DMA read",
        "req_type": "task", "parentId": us_boot["uid"], "status": "done", "estimate": 2,
        "assignee": "firmware.lead", "iteration": "Sprint-1",
        "content": {"description": "Implement I2C DMA read path for BME280 to avoid blocking the main loop.", "rationale": ""}})
    tk_tls = store.create_requirement({"id": "TK-002", "title": "Configure TLS 1.3 for MQTT transport",
        "req_type": "task", "parentId": us_ota["uid"], "status": "in_progress", "estimate": 3,
        "assignee": "firmware.lead", "iteration": "Sprint-2",
        "content": {"description": "Configure Mbed TLS on the MCU for TLS 1.3 with server certificate verification.", "rationale": ""}})

    # Stories -- cloud epic
    us_mqtt = store.create_requirement({"id": "US-004", "title": "Ingest sensor readings via MQTT",
        "req_type": "story", "parentId": ep_cloud["uid"], "status": "backlog", "estimate": 5,
        "assignee": "systems.lead", "iteration": "Sprint-2",
        "content": {"description": "As the cloud platform, I receive sensor readings from all registered devices via MQTT and write them to the time-series store.", "rationale": ""}})
    us_api = store.create_requirement({"id": "US-005", "title": "REST API for device readings",
        "req_type": "story", "parentId": ep_cloud["uid"], "status": "backlog", "estimate": 8,
        "content": {"description": "As a developer, I query the last 24 h of readings for a device via a REST API.", "rationale": ""}})

    # Bug
    bg = store.create_requirement({"id": "BG-001", "title": "Humidity reading drifts +3 % RH after 2 h",
        "req_type": "bug", "parentId": ep_fw["uid"], "status": "in_progress", "priority": "high",
        "assignee": "firmware.lead", "iteration": "Sprint-2",
        "content": {"description": "After 2 h of continuous operation, humidity readings are 3 % RH above reference. Root cause: self-heating from MCU not compensated.", "rationale": ""}})

    # Spike
    sp = store.create_requirement({"id": "SP-001", "title": "Spike: evaluate Thread vs Wi-Fi for battery life",
        "req_type": "spike", "parentId": ep_fw["uid"], "status": "done", "estimate": 3,
        "content": {"description": "Time-box: 3 points. Compare Thread and Wi-Fi current draw on the target MCU. Produce a measurement report.", "rationale": ""}})

    agile_count = len(store.requirements) - r_count

    # -----------------------------------------------------------------------
    # Module: comms-security-baseline
    # A reusable set of communications security requirements that can be
    # included in any product using the same radio stack.
    # -----------------------------------------------------------------------
    import shutil as _shutil
    modules_dir = root / "modules" / "comms-security"
    modules_dir.mkdir(parents=True, exist_ok=True)

    module_manifest = {
        "schema_version": "1.0.0",
        "id": "comms-security",
        "title": "Communications Security Baseline",
        "version": "1.0.0",
        "description": "Reusable communications security requirements applicable to any Wi-Fi/Matter IoT product.",
        "overrideable_fields": ["priority", "owner", "status"],
        "maintainer": "security.lead",
    }
    from .fileio import save_yaml
    save_yaml(modules_dir / "_module.yaml", module_manifest)

    MODULE_REQS = [
        {"id": "MOD-SEC-001", "title": "TLS 1.2+ for all network transport",
         "req_type": "security", "priority": "critical",
         "content": {"description": "All network communication shall use TLS 1.2 or later. TLS 1.0 and 1.1 are prohibited.", "rationale": "TLS 1.0/1.1 have known weaknesses and are prohibited by current security standards."},
         "acceptance_criteria": [{"text": "Network traffic captured under test shows only TLS 1.2+ handshakes.", "uid": "ac-mod-sec-001-1", "id": "AC-1"}]},
        {"id": "MOD-SEC-002", "title": "Certificate validation mandatory",
         "req_type": "security", "priority": "critical",
         "content": {"description": "Devices shall validate server certificates against a trusted CA bundle. Certificate pinning is encouraged for OTA endpoints.", "rationale": "Without certificate validation, devices are vulnerable to MITM attacks."},
         "acceptance_criteria": [{"text": "Connection to a server with an invalid certificate is rejected.", "uid": "ac-mod-sec-002-1", "id": "AC-1"}]},
        {"id": "MOD-SEC-003", "title": "Unique per-device credentials",
         "req_type": "security", "priority": "critical",
         "content": {"description": "No credential (key, certificate, password) shall be shared across more than one device unit.", "rationale": "Universal credentials are prohibited by PSTI Act 2022 and enable fleet-wide compromise."},
         "acceptance_criteria": [{"text": "Provisioning system generates unique X.509 cert per device serial.", "uid": "ac-mod-sec-003-1", "id": "AC-1"}]},
        {"id": "MOD-SEC-004", "title": "Mutual TLS for cloud API",
         "req_type": "security", "priority": "high",
         "content": {"description": "Device-to-cloud API connections shall use mutual TLS (mTLS). The cloud endpoint shall reject connections without a valid device certificate.", "rationale": "mTLS provides device identity assurance to the cloud."},
         "acceptance_criteria": [{"text": "Cloud rejects connections without valid device cert.", "uid": "ac-mod-sec-004-1", "id": "AC-1"}]},
        {"id": "MOD-SEC-005", "title": "MQTT topic ACLs per device",
         "req_type": "security", "priority": "high",
         "content": {"description": "Each device shall only publish to and subscribe from its own topic namespace. Cross-device topic access shall be denied by the broker.", "rationale": "Topic ACLs prevent a compromised device from reading or injecting data for other devices."},
         "acceptance_criteria": [{"text": "Device A cannot publish to Device B topic namespace.", "uid": "ac-mod-sec-005-1", "id": "AC-1"}]},
    ]

    from .fileio import uuid7, utcnow_iso, compute_requirement_hash
    from . import __version__ as TOOL_VERSION

    for mr in MODULE_REQS:
        uid = uuid7()
        now = utcnow_iso()
        data = {
            "schema_version": "1.0.0", "type": "requirement", "tool_version": TOOL_VERSION,
            "uid": uid, "id": mr["id"], "parentId": None,
            "title": mr["title"], "version": "1.0.0",
            "content": mr["content"],
            "acceptance_criteria": mr.get("acceptance_criteria", []),
            "status": "approved", "priority": mr.get("priority", "high"),
            "req_type": mr["req_type"], "owner": "security.lead",
            "relationships": [], "links": [], "attachments": [],
            "dor_checklist": [], "dod_checklist": [],
            "attributes": {}, "custom_fields": {}, "nfr": {},
            "constraints": [], "assumptions": [],
            "risk": "none", "safety_related": False, "safety_classification": None,
            "verification_method": "test",
            "verification": {"status": "not_started", "verified_date": None, "note": ""},
            "approval": {"status": "approved", "approved_by": "security.lead", "approved_date": now},
            "review": {"last_reviewed": now, "reviewers": ["security.lead"], "note": ""},
            "implementation": {"status": "not_started", "branch": None},
            "content_hash": "", "created": now, "last_modified": now, "deleted": False,
            "history": [{"version": "1.0.0", "date": now, "modified_by": "reqtool", "summary": "Initial.", "commit_sha": None, "change_ref": None}],
        }
        data["content_hash"] = compute_requirement_hash(data)
        save_yaml(modules_dir / f"{uid}.yaml", data)

    # Register module in product
    product_path = root / "products" / "env-sensor-v1" / "_product.yaml"
    if product_path.exists():
        from .fileio import load_yaml
        product_data = load_yaml(product_path) or {}
        if "modules" not in product_data:
            product_data["modules"] = []
        product_data["modules"].append({"id": "comms-security", "version": "1.0.0", "overrides": {}})
        save_yaml(product_path, product_data)

    click.echo(click.style(f"Demo repository initialised at {root}", fg="green"))
    click.echo(f"  {r_count} systems requirements  |  {t_count} TBDs  |  {p_count} principles")
    click.echo(f"  {agile_count} agile items (theme → epics → stories/tasks/bug/spike)")
    click.echo(f"  1 module: comms-security ({len(MODULE_REQS)} pre-approved security requirements)")
    click.echo(f"  Product: env-sensor-v1 (includes comms-security module)")
    click.echo(f"  Cross-links: stories satisfy systems requirements via 'satisfies' relationships")
    _print_next_steps(root)


# ---------------------------------------------------------------------------
# init agile
# ---------------------------------------------------------------------------

@init.command("agile")
@click.option("--repo", default=None)
@click.option("--title", default="", help="Repository title.")
@click.option("--id", "repo_id", default="", help="Repository ID (slug).")
def init_agile(repo: Optional[str], title: str, repo_id: str):
    """Initialise with agile workflow types (theme/initiative/epic/feature/story/task/bug/spike).

    Writes agile workflow, type vocabulary, DoR/DoD defaults, and sensible hierarchy.
    """
    from .fileio import load_yaml, save_yaml
    import shutil

    root = Path(repo).resolve() if repo else Path.cwd()
    if (root / ".reqtool" / "config.yaml").exists():
        click.echo(f"Repository already initialised at {root}", err=True)
        sys.exit(1)

    if not repo_id:
        repo_id = click.prompt("Repository ID (slug)", default=root.name)
    if not title:
        title = click.prompt("Repository title", default=repo_id.replace("-", " ").title())

    _write_base_repo(root, repo_id, title)

    defaults_dir = Path(__file__).parent / "defaults"

    # Write enums with agile defaults
    enums = {
        "domain": ["product", "platform", "infrastructure", "security", "data"],
        "discipline": ["BE", "FE", "iOS", "Android", "DevOps", "QA", "Security"],
        "team": ["backend", "frontend", "mobile", "platform", "security", "qa"],
        "owner": [],
        "tags": ["critical-path", "tech-debt", "security", "regulatory", "blocked"],
        "nfr_keys": ["latency_ms", "throughput_rps", "uptime_pct", "error_rate_pct"],
        "estimate_unit": "points",
        "id_domain": {
            "TH": "theme", "IN": "initiative", "EP": "epic",
            "FT": "feature", "US": "story", "TK": "task", "BG": "bug", "SP": "spike",
        },
    }
    save_yaml(root / ".reqtool" / "enums.yaml", enums)

    # Copy hierarchy.yaml
    hierarchy_src = defaults_dir / "hierarchy.yaml"
    if hierarchy_src.exists():
        shutil.copy(str(hierarchy_src), str(root / ".reqtool" / "hierarchy.yaml"))

    # Copy templates
    templates_src = defaults_dir / "templates.yaml"
    if templates_src.exists():
        shutil.copy(str(templates_src), str(root / ".reqtool" / "templates.yaml"))

    click.echo(click.style(f"Initialised agile repository at {root}", fg="green"))
    click.echo(f"  Types: theme, initiative, epic, feature, story, task, bug, spike")
    click.echo(f"  Workflows: lightweight, sprint")
    click.echo(f"  DoR/DoD: story, task, bug, spike, epic")
    click.echo(f"  Estimate unit: points (change in .reqtool/enums.yaml)")
    _print_next_steps(root)


# ---------------------------------------------------------------------------
# init systems
# ---------------------------------------------------------------------------

@init.command("systems")
@click.option("--repo", default=None)
@click.option("--title", default="", help="Repository title.")
@click.option("--id", "repo_id", default="", help="Repository ID (slug).")
def init_systems(repo: Optional[str], title: str, repo_id: str):
    """Initialise with systems engineering defaults and formal review workflow.

    Writes formal/safety-formal workflow, stakeholder_need and requirements types,
    and sensible hierarchy for embedded/IoT/safety-critical programmes.
    """
    from .fileio import load_yaml, save_yaml
    import shutil

    root = Path(repo).resolve() if repo else Path.cwd()
    if (root / ".reqtool" / "config.yaml").exists():
        click.echo(f"Repository already initialised at {root}", err=True)
        sys.exit(1)

    if not repo_id:
        repo_id = click.prompt("Repository ID (slug)", default=root.name)
    if not title:
        title = click.prompt("Repository title", default=repo_id.replace("-", " ").title())

    _write_base_repo(root, repo_id, title)

    defaults_dir = Path(__file__).parent / "defaults"

    # Write enums with systems defaults
    default_enums_path = defaults_dir / "enums.yaml"
    if default_enums_path.exists():
        enums = load_yaml(default_enums_path)
        save_yaml(root / ".reqtool" / "enums.yaml", {
            "domain":       enums.get("domain", []),
            "discipline":   enums.get("discipline", []),
            "team":         enums.get("team", []),
            "owner":        enums.get("owner", []),
            "safety_class": enums.get("safety_class", []),
            "tags":         enums.get("tags", []),
            "nfr_keys":     enums.get("nfr_keys", []),
            "id_domain":    enums.get("id_domain", {}),
            "estimate_unit": "days",
        })
    else:
        _write_enums(root, domains=[])

    # Write formal workflow into config
    default_workflow_path = defaults_dir / "workflow.yaml"
    if default_workflow_path.exists():
        workflow_data = load_yaml(default_workflow_path)
        config_path = root / ".reqtool" / "config.yaml"
        config_data = load_yaml(config_path) or {}
        config_data["workflow"] = workflow_data
        save_yaml(config_path, config_data)

    # Copy hierarchy.yaml
    hierarchy_src = defaults_dir / "hierarchy.yaml"
    if hierarchy_src.exists():
        shutil.copy(str(hierarchy_src), str(root / ".reqtool" / "hierarchy.yaml"))

    # Copy templates and principles
    for fname in ("templates.yaml",):
        src = defaults_dir / fname
        if src.exists():
            shutil.copy(str(src), str(root / ".reqtool" / fname))

    click.echo(click.style(f"Initialised systems engineering repository at {root}", fg="green"))
    click.echo(f"  Types: stakeholder_need, functional, performance, security, safety, interface, compliance, constraint, operational, physical")
    click.echo(f"  Workflows: formal, safety_formal")
    click.echo(f"  Safety formal guards: requires ACs + safety_classification for approval")
    _print_next_steps(root)


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

@cli.group()
def new_agile():
    """Create a new agile item (story, task, bug, spike, epic, feature, theme, initiative)."""


def _make_agile_item(repo: Optional[str], item_type: str) -> None:
    """Shared logic for creating any agile item type interactively."""
    root = Path(repo).resolve() if repo else _repo_root()
    from .store import Store
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
        from .store import Store
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
        from .store import Store
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
        from .store import Store
        store = Store(root)
        store.load()
        result = store.create_tbd(fields)

    click.echo(click.style(f"Created: {result['id']} ({result['uid']})", fg="green"))


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("id_or_uid")
@click.option("--repo", default=None)
def show(id_or_uid: str, repo: Optional[str]):
    """Print an artefact to stdout."""
    root = Path(repo).resolve() if repo else _repo_root()

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
    else:
        from .store import Store
        store = Store(root)
        store.load()
        for collection in (store.requirements, store.principles, store.tbds):
            for uid, item in collection.items():
                if uid == id_or_uid or item.get("id") == id_or_uid:
                    click.echo(json.dumps(item, indent=2, default=str))
                    return

    click.echo(f"Not found: {id_or_uid}", err=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("id_or_uid")
@click.option("--repo", default=None)
def history(id_or_uid: str, repo: Optional[str]):
    """Print git log for an artefact."""
    root = Path(repo).resolve() if repo else _repo_root()
    from .store import Store
    from .git_ops import git_log
    store = Store(root)
    store.load()

    uid = None
    for collection in (store.requirements, store.principles, store.tbds):
        for item_uid, item in collection.items():
            if item_uid == id_or_uid or item.get("id") == id_or_uid:
                uid = item_uid
                break
        if uid:
            break

    if uid is None:
        click.echo(f"Not found: {id_or_uid}", err=True)
        sys.exit(1)

    for get_path in (store.req_path, store.principle_path, store.tbd_path):
        p = get_path(uid)
        if p.exists():
            entries = git_log(root, p)
            for e in entries:
                click.echo(f"{e['sha'][:7]}  {e['date'][:10]}  {e['author_name']}  {e['subject']}")
            return

    click.echo("No git history found (file not yet committed).")


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, show_default=True)
@click.option("--reload", is_flag=True, default=False, help="Enable uvicorn auto-reload (dev).")
def serve(repo: Optional[str], host: str, port: int, reload: bool):
    """Start the backend API and UI server."""
    import uvicorn
    from . import __version__
    from .store import Store
    from pathlib import Path as _Path

    root = _Path(repo).resolve() if repo else _repo_root()
    os.environ["REQTOOL_REPO"] = str(root)

    # Load store just enough to read counts and config for the banner
    try:
        _store = Store(root)
        _store.load()
        _req_count = len([r for r in _store.requirements.values() if not r.get("deleted")])
        _principle_count = len([p for p in _store.principles.values() if not p.get("deleted")])
        _tbd_count = len([t for t in _store.tbds.values() if not t.get("deleted")])
        _repo_title = _store.config.repo_title or _store.config.repo_id or root.name
        _has_ui = (_Path(__file__).parent / "ui" / "dist").exists()
        _type_count = len(_store.hierarchy.types)
        _validation = _store.config.validation
        del _store  # release before uvicorn starts its own instance
    except Exception:
        _req_count = _principle_count = _tbd_count = _type_count = 0
        _repo_title = root.name
        _has_ui = False

    # -----------------------------------------------------------------------
    # Startup banner
    # -----------------------------------------------------------------------
    W = 58  # banner width
    SEP = click.style("─" * W, fg="bright_black")
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
        click.echo("  " + click.style("⚠  auto-reload enabled (dev mode)", fg="yellow"))
    click.echo(SEP)
    click.echo(click.style("  Press Ctrl+C to stop.", fg="bright_black"))
    click.echo("")

    uvicorn.run(
        "reqtool.main:app_factory",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_level="info",
    )


@cli.command()
@click.option("--since", default="HEAD~1", help="Git ref to diff against (commit SHA, tag, or HEAD~N).")
@click.option("--repo", default=None)
def diff(since: str, repo: Optional[str]):
    """Show requirement changes since a git ref.

    \b
    Examples:
      req diff                    # changes since last commit
      req diff --since HEAD~5     # last 5 commits
      req diff --since baseline/v1.0-rc1
      req diff --since abc1234
    """
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
                       f"  v{c.get('version_from','?')} → v{c.get('version_to','?')}")
            for field, delta in c.get("changes", {}).items():
                from_s = str(delta.get("from",""))[:60]
                to_s   = str(delta.get("to",""))[:60]
                click.echo(f"      {field}:")
                click.echo(click.style(f"        - {from_s}", fg="red"))
                click.echo(click.style(f"        + {to_s}", fg="green"))


@cli.command()
@click.option("--repo", default=None)
def stats(repo: Optional[str]):
    """Print a quick metrics summary to stdout.

    Useful in CI to assert quality gates:

    \b
      req stats | grep "Approved" # check approval rate
    """
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





@cli.command()
@click.option("--output", "-o", default="openapi.yaml", show_default=True, help="Output file path.")
@click.option("--format", "fmt", type=click.Choice(["yaml", "json"]), default="yaml", show_default=True)
@click.option("--repo", default=None)
def openapi(output: str, fmt: str, repo: Optional[str]):
    """Export the OpenAPI specification to a file.

    The spec is generated from the live FastAPI application and reflects the
    exact types of all request/response bodies. Use it to generate typed clients
    or validate integrations.

    Example -- generate a TypeScript client with openapi-ts:

    \b
        req openapi -o openapi.yaml
        npx @hey-api/openapi-ts -i openapi.yaml -o src/client -c fetch
    """
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
            import json, sys
            click.echo("ruamel.yaml not available, falling back to JSON", err=True)
            out_path = out_path.with_suffix(".json")
            out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    else:
        import json
        out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    click.echo(click.style(f"OpenAPI spec written: {out_path}", fg="green"))
    click.echo(f"  Paths: {len(schema.get('paths', {}))}")
    click.echo(f"  Version: {schema.get('info', {}).get('version', '?')}")


if __name__ == "__main__":
    cli()
