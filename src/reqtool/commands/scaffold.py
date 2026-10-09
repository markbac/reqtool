"""
reqtool.commands.scaffold
=========================
Scaffolding helpers and repository initialization subcommands.
"""

from __future__ import annotations

import sys
import shutil
from pathlib import Path
from typing import Optional
import click

from ..repo_init import write_base_repo as _write_base_repo
from ..repo_init import write_enums as _write_enums
from ..repo_init import write_product as _write_product
from .common import cli
from .scaffold_demo import populate_demo_data


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
    """
    from ..fileio import save_yaml, load_yaml
    from ..store import Store

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
    defaults_dir = Path(__file__).parent.parent / "defaults"
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

    if default_hierarchy_path.exists():
        shutil.copy(str(default_hierarchy_path), str(root / ".reqtool" / "hierarchy.yaml"))

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

    by_domain: dict[str, int] = {}
    for p in store.principle_map().values():
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
    """Initialise with the full IoT environmental sensor demo dataset."""
    from ..store import Store
    from ..fileio import load_yaml, save_yaml

    root = Path(repo).resolve() if repo else Path.cwd()
    if (root / ".reqtool" / "config.yaml").exists():
        click.echo(f"Repository already initialised at {root}", err=True)
        sys.exit(1)

    _write_base_repo(root, "iot-sensor", "IoT Environmental Sensor Platform")
    _cfg = load_yaml(root / ".reqtool" / "config.yaml") or {}
    _cfg["repo_description"] = (
        "Production-grade IoT Environmental Sensor Platform supporting Matter over Thread, Wi-Fi 6, "
        "and MQTT/TLS cloud telemetry. Features ultra-low-power coin-cell power management, UK PSTI / EU RED "
        "cybersecurity baselines, ISO 26262 safety classifications, and ATAM Architecture Tradeoff Analysis."
    )
    _cfg.setdefault("validation", {}).update({
        "require_owner": False,
        "warn_on_missing_test_ref": False,
    })
    save_yaml(root / ".reqtool" / "config.yaml", _cfg)
    _write_enums(root,
        domains=["need","sensing","comms","power","mechanical","thermal",
                 "industrial","security","safety","compliance","ux",
                 "manufacture","identity","firmware","data","cost","system"],
        nfr_keys=["sampling_rate_hz","accuracy_degc","accuracy_rh_pct","accuracy_hpa",
                  "battery_life_months","setup_time_minutes","latency_ms",
                  "range_m","ip_rating","mtbf_hours","mass_g","battery_count"],
        id_domain={"N":"N","SR":"SR","SYS":"SYS","DR":"DR"},
    )
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
    populate_demo_data(root, store)
    _print_next_steps(root)


@init.command("agile")
@click.option("--repo", default=None)
@click.option("--title", default="", help="Repository title.")
@click.option("--id", "repo_id", default="", help="Repository ID (slug).")
def init_agile(repo: Optional[str], title: str, repo_id: str):
    """Initialise with agile workflow types."""
    from ..fileio import save_yaml

    root = Path(repo).resolve() if repo else Path.cwd()
    if (root / ".reqtool" / "config.yaml").exists():
        click.echo(f"Repository already initialised at {root}", err=True)
        sys.exit(1)

    if not repo_id:
        repo_id = click.prompt("Repository ID (slug)", default=root.name)
    if not title:
        title = click.prompt("Repository title", default=repo_id.replace("-", " ").title())

    _write_base_repo(root, repo_id, title)

    defaults_dir = Path(__file__).parent.parent / "defaults"

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

    hierarchy_src = defaults_dir / "hierarchy.yaml"
    if hierarchy_src.exists():
        shutil.copy(str(hierarchy_src), str(root / ".reqtool" / "hierarchy.yaml"))

    templates_src = defaults_dir / "templates.yaml"
    if templates_src.exists():
        shutil.copy(str(templates_src), str(root / ".reqtool" / "templates.yaml"))

    click.echo(click.style(f"Initialised agile repository at {root}", fg="green"))
    click.echo(f"  Types: theme, initiative, epic, feature, story, task, bug, spike")
    click.echo(f"  Workflows: lightweight, sprint")
    click.echo(f"  DoR/DoD: story, task, bug, spike, epic")
    click.echo(f"  Estimate unit: points (change in .reqtool/enums.yaml)")
    _print_next_steps(root)


@init.command("systems")
@click.option("--repo", default=None)
@click.option("--title", default="", help="Repository title.")
@click.option("--id", "repo_id", default="", help="Repository ID (slug).")
def init_systems(repo: Optional[str], title: str, repo_id: str):
    """Initialise with systems engineering defaults and formal review workflow."""
    from ..fileio import load_yaml, save_yaml

    root = Path(repo).resolve() if repo else Path.cwd()
    if (root / ".reqtool" / "config.yaml").exists():
        click.echo(f"Repository already initialised at {root}", err=True)
        sys.exit(1)

    if not repo_id:
        repo_id = click.prompt("Repository ID (slug)", default=root.name)
    if not title:
        title = click.prompt("Repository title", default=repo_id.replace("-", " ").title())

    _write_base_repo(root, repo_id, title)

    defaults_dir = Path(__file__).parent.parent / "defaults"

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

    default_workflow_path = defaults_dir / "workflow.yaml"
    if default_workflow_path.exists():
        workflow_data = load_yaml(default_workflow_path)
        config_path = root / ".reqtool" / "config.yaml"
        config_data = load_yaml(config_path) or {}
        config_data["workflow"] = workflow_data
        save_yaml(config_path, config_data)

    hierarchy_src = defaults_dir / "hierarchy.yaml"
    if hierarchy_src.exists():
        shutil.copy(str(hierarchy_src), str(root / ".reqtool" / "hierarchy.yaml"))

    for fname in ("templates.yaml",):
        src = defaults_dir / fname
        if src.exists():
            shutil.copy(str(src), str(root / ".reqtool" / fname))

    click.echo(click.style(f"Initialised systems engineering repository at {root}", fg="green"))
    click.echo(f"  Types: stakeholder_need, functional, performance, security, safety, interface, compliance, constraint, operational, physical")
    click.echo(f"  Workflows: formal, safety_formal")
    click.echo(f"  Safety formal guards: requires ACs + safety_classification for approval")
    _print_next_steps(root)
