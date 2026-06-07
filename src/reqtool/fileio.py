"""
reqtool.fileio
==============
YAML file I/O, UUIDv7 generation, and content hash computation.
Uses ruamel.yaml for round-trip comment preservation on write.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

# Hashed fields for requirements (spec §6)
_REQ_HASHED_FIELDS: set[str] = {
    # Identity
    "id", "title", "parentId",
    # Core content
    "content", "acceptance_criteria",
    # Classification -- all affect what the requirement means
    "req_type", "domain", "discipline", "feature", "component",
    "status", "priority", "risk",
    # Ownership
    "owner", "allocated_to", "tags",
    # Safety
    "safety_related", "safety_classification",
    # Verification
    "verification_method",
    # Traceability
    "relationships", "links", "attachments",
    # Constraints and NFR
    "constraints", "assumptions", "nfr", "attributes", "custom_fields",
}

_PRINCIPLE_HASHED_FIELDS: set[str] = {
    "id", "title", "content", "status", "domain",
}

_TBD_HASHED_FIELDS: set[str] = {
    "id", "title", "content", "status", "priority",
}

_MODULE_HASHED_FIELDS: set[str] = {
    "id", "title", "content", "requirements", "overrideable",
}

_PRODUCT_HASHED_FIELDS: set[str] = {
    "id", "title", "content", "variants", "modules", "root_requirements",
}


def _yaml_instance() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.preserve_quotes = True
    y.width = 120
    return y


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return as a plain dict."""
    y = _yaml_instance()
    with path.open("r", encoding="utf-8") as fh:
        data = y.load(fh)
    return _to_plain(data)


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict to YAML. Creates parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    y = _yaml_instance()
    with path.open("w", encoding="utf-8") as fh:
        y.dump(data, fh)


def _to_plain(obj: Any) -> Any:
    """Recursively convert ruamel objects to plain Python types."""
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# UUIDv7
# ---------------------------------------------------------------------------

def uuid7() -> str:
    """
    Generate a UUIDv7 string.

    UUIDv7 is not natively available until Python 3.13.
    This implementation follows the draft RFC: 48-bit ms timestamp,
    4-bit version (7), 12-bit random, 2-bit variant, 62-bit random.
    """
    ms = int(time.time() * 1000)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF  # 12 bits
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF  # 62 bits

    time_high = (ms >> 16) & 0xFFFFFFFF
    time_mid = ms & 0xFFFF

    # Build 128-bit integer
    val = (time_high << 96) | (time_mid << 80) | (0x7 << 76) | (rand_a << 64)
    val |= (0b10 << 62) | rand_b

    hex_str = f"{val:032x}"
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------

def _canonical(obj: Any) -> Any:
    """Convert to a JSON-serialisable form with sorted keys."""
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_canonical(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def compute_hash(data: dict[str, Any], hashed_fields: set[str]) -> str:
    """
    Compute SHA-256 over the hashed fields of an artefact dict.
    Returns a hex string prefixed with 'sha256:'.
    """
    subset = {k: data[k] for k in hashed_fields if k in data}
    canonical = _canonical(subset)
    serialised = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_requirement_hash(data: dict[str, Any]) -> str:
    return compute_hash(data, _REQ_HASHED_FIELDS)


def compute_principle_hash(data: dict[str, Any]) -> str:
    return compute_hash(data, _PRINCIPLE_HASHED_FIELDS)


def compute_tbd_hash(data: dict[str, Any]) -> str:
    return compute_hash(data, _TBD_HASHED_FIELDS)


def compute_module_hash(data: dict[str, Any]) -> str:
    return compute_hash(data, _MODULE_HASHED_FIELDS)


def compute_product_hash(data: dict[str, Any]) -> str:
    return compute_hash(data, _PRODUCT_HASHED_FIELDS)


def verify_hash(data: dict[str, Any], artefact_type: str) -> bool:
    """Return True if the stored content_hash matches recomputation."""
    stored = data.get("content_hash", "")
    fn_map = {
        "requirement": compute_requirement_hash,
        "principle": compute_principle_hash,
        "tbd": compute_tbd_hash,
        "module": compute_module_hash,
        "product": compute_product_hash,
    }
    fn = fn_map.get(artefact_type)
    if fn is None:
        return True
    return fn(data) == stored


# ---------------------------------------------------------------------------
# Version bumping
# ---------------------------------------------------------------------------

def bump_version(current: str, increment: str) -> str:
    """Increment a semver string by patch/minor/major."""
    parts = current.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if increment == "major":
        return f"{major + 1}.0.0"
    if increment == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
