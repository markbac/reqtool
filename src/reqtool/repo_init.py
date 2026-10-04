"""
reqtool.repo_init
=================
Writes the files of a new repository (configuration, enums, a product manifest).
Shared by the ``req init`` commands and the ``/repo/init`` API, so neither imports the other.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import __version__


def write_base_repo(root: Path, repo_id: str, title: str, theme: str = "dark") -> None:
    """Shared scaffold used by all init variants."""
    from .fileio import save_yaml

    for d in ("requirements", "principles", "decisions", "modules", "products", ".reqtool", "exports"):
        (root / d).mkdir(parents=True, exist_ok=True)

    config = {
        "schema_version": "1.0.0",
        "repo_id": repo_id,
        "repo_title": title,
        "repo_description": "",
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
    from .auth import ensure_secrets_ignored
    ensure_secrets_ignored(root)  # never commit .reqtool/.secret_key or users.yaml

    gitattributes = root / ".gitattributes"
    if not gitattributes.exists():
        gitattributes.write_text(
            "# reqtool Git LFS tracking rules for binary attachments\n"
            "attachments/*/*.png  filter=lfs diff=lfs merge=lfs -text\n"
            "attachments/*/*.jpg  filter=lfs diff=lfs merge=lfs -text\n"
            "attachments/*/*.jpeg filter=lfs diff=lfs merge=lfs -text\n"
            "attachments/*/*.gif  filter=lfs diff=lfs merge=lfs -text\n"
            "attachments/*/*.pdf  filter=lfs diff=lfs merge=lfs -text\n"
            "attachments/*/*.zip  filter=lfs diff=lfs merge=lfs -text\n"
            "attachments/*/*.step filter=lfs diff=lfs merge=lfs -text\n"
            "attachments/*/*.svg  filter=lfs diff=lfs merge=lfs -text\n"
        )

    # Initialize Git repository and Git LFS if available
    try:
        import subprocess
        if shutil.which("git"):
            subprocess.run(["git", "init"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if shutil.which("git-lfs"):
                subprocess.run(["git", "lfs", "install", "--local"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def write_enums(root: Path, domains: list, nfr_keys: list = None, id_domain: dict = None) -> None:
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


def write_product(root: Path, product_id: str, title: str) -> None:
    from .fileio import save_yaml, utcnow_iso, uuid7
    prod_dir = root / "products" / product_id
    prod_dir.mkdir(parents=True, exist_ok=True)
    now = utcnow_iso()
    save_yaml(prod_dir / "_product.yaml", {
        "schema_version": "1.0.0", "type": "product", "tool_version": __version__,
        "uid": uuid7(), "id": product_id, "title": title, "version": "1.0.0",
        "content": {"description": ""},
        "modules": [], "root_requirements": [], "display_order": [],
        "content_hash": "", "created": now, "last_modified": now, "history": [],
    })
