"""
reqtool.layout
==============
Where each kind of record lives in a repository (#380)::

    requirements/<uid>.yaml                  stakeholder needs and system requirements
    requirements/modules/<id>/_module.yaml   a module's manifest
    requirements/modules/<id>/<uid>.yaml     the module's requirements
    work/<uid>.yaml                          themes, initiatives, epics, features, stories, tasks, defects, spikes, issues
    decisions/  principles/  products/<id>/

Every record in ``requirements/`` and ``work/`` is ``type: requirement``; the folder follows the family of its
``req_type``. Repositories from before this layout keep working: work items in ``requirements/`` and modules in
``modules/<id>/`` still load, and ``req migrate`` moves them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

REQUIREMENTS_DIR = "requirements"
WORK_DIR = "work"
MODULES_DIR = "requirements/modules"
LEGACY_MODULES_DIR = "modules"

# Folders that hold requirement-kind records, and every folder that holds artefacts.
ITEM_DIRS = (REQUIREMENTS_DIR, WORK_DIR)
ARTEFACT_DIRS = (REQUIREMENTS_DIR, WORK_DIR, "principles", "decisions", LEGACY_MODULES_DIR, "products")

# The default family of each built-in type. A type in hierarchy.yaml can set ``family`` to override it.
WORK_TYPES = frozenset({"theme", "initiative", "epic", "feature", "story", "task", "bug", "spike", "issue"})


def family(req_type: Optional[str], hierarchy: Any = None) -> str:
    """``work`` or ``requirement`` for a type, from hierarchy.yaml when it says, else the built-in default."""
    types = getattr(hierarchy, "types", None) or {}
    cfg = types.get(req_type or "") if isinstance(types, dict) else None
    chosen = getattr(cfg, "family", None) if cfg is not None else None
    if chosen in ("work", "requirement"):
        return chosen
    return "work" if req_type in WORK_TYPES else "requirement"


def item_dir(root: Path, req_type: Optional[str], hierarchy: Any = None) -> Path:
    """The folder a record of ``req_type`` belongs in."""
    return root / (WORK_DIR if family(req_type, hierarchy) == "work" else REQUIREMENTS_DIR)


def module_dir(root: Path, module_id: str) -> Path:
    """The folder of a module: the legacy ``modules/<id>`` while it still exists there, else the new place."""
    legacy = root / LEGACY_MODULES_DIR / module_id
    return legacy if legacy.is_dir() else root / MODULES_DIR / module_id


def module_dirs(root: Path) -> list[Path]:
    """Every module folder, new place first; a module in both places is read from the new one."""
    seen: dict[str, Path] = {}
    for base in (root / MODULES_DIR, root / LEGACY_MODULES_DIR):
        if base.is_dir():
            for d in sorted(p for p in base.iterdir() if p.is_dir()):
                seen.setdefault(d.name, d)
    return list(seen.values())


def is_module_path(rel: Path) -> bool:
    """True for a path (relative to the root) inside a module folder, old or new."""
    parts = rel.parts
    return (len(parts) >= 2 and parts[0] == LEGACY_MODULES_DIR) or (len(parts) >= 3 and parts[:2] == ("requirements", "modules"))


def is_item_file(rel: str) -> bool:
    """True for a requirement or work item file (relative to the root, ``/`` separated), not a module's (#380)."""
    head, _, name = rel.rpartition("/")
    return head in ITEM_DIRS and name.endswith(".yaml")
