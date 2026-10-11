"""Principle areas, categories and the default packs.

A principle sits in an **area** (Architecture) and a **category** inside it (Security). The areas and
categories a repository uses are its *vocabulary*, kept under ``principle_areas`` in ``.reqtool/enums.yaml``.
A repository without one uses the default vocabulary, which is what the packs in ``defaults/principles``
define. Everything here is pure: the store and the services do the reading and writing.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .fileio import load_yaml

PACK_DIR = Path(__file__).parent / "defaults" / "principles"

# Order the areas are shown in, and the packs `req init` offers.
AREA_ORDER = (
    "business", "product", "architecture", "software_engineering", "hardware_firmware",
    "security", "data_privacy", "delivery", "operations", "safety_quality",
)

# Packs `req init` includes unless told otherwise, by flavour.
FLAVOUR_PACKS: dict[str, tuple[str, ...]] = {
    "defaults": AREA_ORDER,
    "agile": ("business", "product", "architecture", "software_engineering", "security",
              "data_privacy", "delivery", "operations"),
    "systems": ("business", "architecture", "software_engineering", "hardware_firmware", "security",
                "data_privacy", "delivery", "operations", "safety_quality"),
}

GENERAL = "general"

# Where a principle that only has the old single ``domain`` goes. Security is a category of Architecture.
LEGACY_DOMAINS: dict[str, tuple[str, str]] = {
    "business": ("business", GENERAL),
    "architecture": ("architecture", GENERAL),
    "security": ("architecture", "security"),
    "firmware": ("hardware_firmware", GENERAL),
    "comms": ("architecture", "integration"),
    "data": ("data_privacy", GENERAL),
    "process": ("delivery", GENERAL),
    "safety": ("safety_quality", GENERAL),
}

Vocabulary = dict[str, dict[str, Any]]   # area -> {"label", "code", "categories": {category: {"label", "code"}}}


# ---------------------------------------------------------------------------
# Packs
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _packs() -> dict[str, dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = {}
    for path in sorted(PACK_DIR.glob("*.yaml")):
        data = load_yaml(path)
        packs[data["area"]] = data
    return packs


def pack_areas() -> list[str]:
    """Areas that have a pack, in display order."""
    found = _packs()
    return [a for a in AREA_ORDER if a in found] + sorted(a for a in found if a not in AREA_ORDER)


def load_pack(area: str) -> dict[str, Any]:
    try:
        return _packs()[area]
    except KeyError:
        raise KeyError(f"No principle pack for area '{area}'. Available: {', '.join(pack_areas())}") from None


def pack_principles(area: str) -> list[dict[str, Any]]:
    """The pack's principles as store-ready fields, placed in the area."""
    out = []
    for p in load_pack(area)["principles"]:
        out.append({
            "id": p["id"], "title": p["title"], "area": area, "category": p["category"],
            "content": {k: (p.get(k) or "").strip() for k in ("description", "rationale", "implications", "exceptions")},
        })
    return out


def pack_summary(area: str) -> dict[str, Any]:
    pack = load_pack(area)
    counts: dict[str, int] = {}
    for p in pack["principles"]:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    return {
        "area": area, "label": pack.get("label", area), "code": pack.get("code", ""),
        "description": pack.get("description", ""), "count": len(pack["principles"]),
        "categories": [{"id": c["id"], "label": c.get("label", c["id"]), "count": counts.get(c["id"], 0)}
                       for c in pack["categories"]],
    }


@lru_cache(maxsize=1)
def _pack_index() -> dict[str, tuple[str, str]]:
    return {p["id"]: (area, p["category"]) for area, pack in _packs().items() for p in pack["principles"]}


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

def default_vocabulary(areas: Optional[Iterable[str]] = None) -> Vocabulary:
    """The vocabulary the packs define, for ``areas`` (default: all of them)."""
    wanted = list(areas) if areas is not None else pack_areas()
    out: Vocabulary = {}
    for area in wanted:
        pack = load_pack(area)
        out[area] = {
            "label": pack.get("label", area), "code": pack.get("code", ""),
            "categories": {c["id"]: {"label": c.get("label", c["id"]), "code": c.get("code", "")}
                           for c in pack["categories"]},
        }
    return out


def effective_vocabulary(repo_areas: Optional[Mapping[str, Any]]) -> Vocabulary:
    """The repository's own vocabulary, or the default one when it has none."""
    if repo_areas:
        return clean_vocabulary(repo_areas)
    return default_vocabulary()


def clean_vocabulary(raw: Mapping[str, Any]) -> Vocabulary:
    """Normalise a vocabulary read from YAML or an API body. Raises ValueError for a malformed one."""
    out: Vocabulary = {}
    for area, spec in raw.items():
        if not _SLUG.fullmatch(str(area)):
            raise ValueError(f"Area id '{area}' must be lower case letters, digits and underscores")
        spec = spec if isinstance(spec, Mapping) else {}
        cats: dict[str, dict[str, str]] = {}
        for cat, cspec in (spec.get("categories") or {}).items():
            if not _SLUG.fullmatch(str(cat)):
                raise ValueError(f"Category id '{cat}' in '{area}' must be lower case letters, digits and underscores")
            cspec = cspec if isinstance(cspec, Mapping) else {}
            cats[str(cat)] = {"label": str(cspec.get("label") or _titled(cat)), "code": str(cspec.get("code") or _code(cat))}
        out[str(area)] = {"label": str(spec.get("label") or _titled(area)), "code": str(spec.get("code") or _code(area)),
                          "categories": cats}
    return out


_SLUG = re.compile(r"[a-z][a-z0-9_]*")


def _titled(slug: str) -> str:
    return str(slug).replace("_", " ").capitalize()


def _code(slug: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(slug).upper())[:5]


def merge_pack_into(vocabulary: Vocabulary, area: str) -> Vocabulary:
    """``vocabulary`` plus the area and categories of a pack (existing entries are kept as they are)."""
    out = {a: {**v, "categories": dict(v.get("categories", {}))} for a, v in vocabulary.items()}
    pack = default_vocabulary([area])[area]
    mine = out.setdefault(area, {"label": pack["label"], "code": pack["code"], "categories": {}})
    for cat, spec in pack["categories"].items():
        mine["categories"].setdefault(cat, spec)
    return out


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------

def legacy_placement(domain: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    return LEGACY_DOMAINS.get(str(domain or "").strip().lower(), (None, None))


def placement(principle: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Area and category of a principle: as stored, else from the default packs by id, else from its old domain."""
    area, category = principle.get("area"), principle.get("category")
    if area:
        return area, category or GENERAL
    known = _pack_index().get(str(principle.get("id") or ""))
    if known:
        return known
    return legacy_placement(principle.get("domain"))


def normalise_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Fill ``area`` and ``category`` from the old ``domain`` when only that was given. Returns a new dict."""
    out = dict(fields)
    if not out.get("area") and (out.get("domain") or out.get("id")):
        area, category = placement({"id": out.get("id"), "domain": out.get("domain")})
        if area:
            out["area"] = area
            out.setdefault("category", category)
    if out.get("area") and not out.get("category"):
        out["category"] = GENERAL
    return out


def check_placement(area: Optional[str], category: Optional[str], vocabulary: Mapping[str, Any]) -> Optional[str]:
    """A message when the area or category is not in the vocabulary, else None. An unplaced principle is fine."""
    if not area:
        return None
    spec = vocabulary.get(area)
    if spec is None:
        return f"Area '{area}' is not in the principle vocabulary"
    if category and category not in (spec.get("categories") or {}):
        return f"Category '{category}' is not in the '{area}' area of the principle vocabulary"
    return None


def make_id(area: str, category: str, title: str, vocabulary: Mapping[str, Any], taken: Iterable[str]) -> str:
    """``P-<AREA>-<CATEGORY>-<SLUG>``, made unique among ``taken``."""
    spec = vocabulary.get(area, {})
    a_code = spec.get("code") or _code(area)
    c_code = (spec.get("categories", {}).get(category, {}) or {}).get("code") or _code(category)
    slug = re.sub(r"[^A-Z0-9]+", "-", title.upper()).strip("-")[:28].strip("-") or "NEW"
    base = f"P-{a_code}-{c_code}-{slug}"
    used = set(taken)
    candidate, n = base, 2
    while candidate in used:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

UNPLACED = "unplaced"


def with_placement(principle: Mapping[str, Any]) -> dict[str, Any]:
    """A copy with ``area`` and ``category`` filled in when they can be worked out (``placement_derived`` says so)."""
    out = dict(principle)
    if not out.get("area"):
        area, category = placement(out)
        if area:
            out["area"], out["category"], out["placement_derived"] = area, category, True
    return out


def area_tree(principles: Iterable[Mapping[str, Any]], vocabulary: Mapping[str, Any]) -> dict[str, Any]:
    """Areas, categories and counts: the vocabulary in order, then anything in use that it does not know."""
    counts: dict[tuple[str, str], int] = {}
    for p in principles:
        area, category = placement(p)
        key = (area or UNPLACED, category or GENERAL)
        counts[key] = counts.get(key, 0) + 1

    def build(area: str, spec: Mapping[str, Any], known: bool) -> dict[str, Any]:
        cats = []
        listed = dict(spec.get("categories") or {})
        for cat in sorted(c for (a, c) in counts if a == area and c not in listed):
            listed[cat] = {"label": _titled(cat), "code": "", "unknown": True}
        for cat, cspec in listed.items():
            cats.append({"id": cat, "label": cspec.get("label") or _titled(cat), "code": cspec.get("code", ""),
                         "count": counts.get((area, cat), 0), "known": not cspec.get("unknown")})
        return {"id": area, "label": spec.get("label") or _titled(area), "code": spec.get("code", ""),
                "count": sum(c["count"] for c in cats), "known": known, "categories": cats}

    areas = [build(a, spec, True) for a, spec in vocabulary.items()]
    extra = sorted({a for (a, _c) in counts if a not in vocabulary and a != UNPLACED})
    areas += [build(a, {"label": _titled(a)}, False) for a in extra]
    unplaced = sum(n for (a, _c), n in counts.items() if a == UNPLACED)
    return {"areas": areas, "unplaced": unplaced, "total": sum(counts.values())}
