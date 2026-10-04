"""
reqtool.fileio
==============
YAML file I/O, UUIDv7 generation, and content hash computation.
Uses ruamel.yaml for round-trip comment preservation on write.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timezone
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
    # Safety and Compliance
    "safety_related", "safety_classification", "safety_standard", "asil_level", "dal_level", "mitigates_hazard",
    "source_document", "legal_compliance_status", "compliance_rationale",
    # Verification
    "verification_method",
    # Traceability
    "relationships", "links", "attachments",
    # Planning and Release
    "target_release", "target_milestone", "release_status", "planned_start_date", "planned_completion_date",
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


_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


class InvalidId(ValueError):
    """A user-supplied identifier is not safe to use as a single path segment."""


def validate_id(value: str, what: str = "id") -> str:
    """Return ``value`` if it is a safe single path segment, else raise InvalidId.

    Allows letters, digits, ``_``, ``.`` and ``-`` (not leading), max 64 chars.
    Rejects separators, ``..``, whitespace and anything else.
    """
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value) or ".." in value:
        raise InvalidId(f"Invalid {what}: {value!r}")
    return value


def _yaml_instance() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.preserve_quotes = True
    y.width = 120
    return y


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return it as plain Python types.

    Uses ruamel's safe loader, which runs on libyaml when ``ruamel.yaml.clib`` is installed (several
    times faster than the round-trip loader) and keeps YAML 1.2 rules, so values read are identical.
    Comments are not preserved, and files are always rewritten from the plain data anyway.
    """
    y = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as fh:
        data = y.load(fh)
    return _to_plain(data)


def save_yaml(path: Path, data: Any) -> None:
    """Write a dict to YAML atomically. Creates parent directories if needed.

    The document is serialised in memory first, written to a temporary file in
    the same directory, fsynced, then moved over the target with os.replace so
    a crash or serialisation error can never leave a truncated file behind.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    _yaml_instance().dump(data, buf)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as fh:
            fh.write(buf.getvalue())
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _to_plain(obj: Any) -> Any:
    """Recursively convert ruamel objects to plain Python types."""
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]
    if isinstance(obj, date) and not isinstance(obj, datetime):
        # An unquoted YAML date (2026-10-01): keep it a string like every other date field.
        return obj.isoformat()
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
    if isinstance(obj, (datetime, date)):
        # An unquoted YAML date (2026-10-01) loads as a date: hash it as the ISO string it would be if quoted.
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
    rels = data.get("relationships")
    if isinstance(rels, list) and any(isinstance(r, dict) and ("suspect" in r or "_display" in r) for r in rels):
        # Review flags and display text are not content: flagging a link must not change the hash.
        data = {**data, "relationships": [
            {k: v for k, v in r.items() if k not in ("suspect", "_display")} if isinstance(r, dict) else r
            for r in rels]}
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
# Version bumping & SemVer 2.0.0
# ---------------------------------------------------------------------------

def parse_semver(version_str: str) -> dict[str, Any]:
    """Parse a SemVer 2.0.0 version string into components."""
    if not version_str:
        return {"major": 0, "minor": 1, "patch": 0, "prerelease": None, "build_metadata": None, "raw": "0.1.0"}

    main_and_pre, _, build_meta = version_str.partition("+")
    main, _, prerelease = main_and_pre.partition("-")

    parts = main.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    return {
        "major": major,
        "minor": minor,
        "patch": patch,
        "prerelease": prerelease or None,
        "build_metadata": build_meta or None,
        "raw": version_str,
    }


def format_semver(
    major: int,
    minor: int,
    patch: int,
    prerelease: str | None = None,
    build_metadata: str | None = None,
) -> str:
    """Format SemVer components into a compliant SemVer 2.0.0 string."""
    res = f"{major}.{minor}.{patch}"
    if prerelease:
        res += f"-{prerelease}"
    if build_metadata:
        res += f"+{build_metadata}"
    return res


def bump_version(
    current: str,
    increment: str = "patch",
    prerelease: str | None = None,
    build_metadata: str | None = None,
) -> str:
    """
    Increment a semver string by major/minor/patch, with optional prerelease and build metadata.
    """
    parsed = parse_semver(current)
    major, minor, patch = parsed["major"], parsed["minor"], parsed["patch"]

    if increment == "major":
        major += 1
        minor = 0
        patch = 0
    elif increment == "minor":
        minor += 1
        patch = 0
    elif increment == "patch":
        patch += 1

    b_meta = build_metadata if build_metadata is not None else parsed["build_metadata"]
    p_release = prerelease if prerelease is not None else parsed["prerelease"]

    return format_semver(major, minor, patch, prerelease=p_release, build_metadata=b_meta)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
