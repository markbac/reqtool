"""
reqtool.features.query
======================
A small query language for requirements (FEAT-09)::

    status:approved type:safety no:verification "brake pedal" -tag:legacy

Terms are ANDed. ``key:value`` matches a field (case-insensitive), ``no:field`` finds items where the
field is empty, ``has:field`` where it is set, a leading ``-`` negates, and bare words search the
title and description.
"""

from __future__ import annotations

import shlex
from typing import Any, Callable

FIELD_ALIASES = {"type": "req_type", "owner": "owner", "id": "id", "status": "status", "priority": "priority",
                 "tag": "tags", "tags": "tags", "module": "module", "safety": "safety_related"}


class QueryError(ValueError):
    pass


def _value(req: dict[str, Any], field: str) -> Any:
    if field == "verification":
        return (req.get("verification") or {}).get("status")
    if field == "description":
        return (req.get("content") or {}).get("description")
    if field in ("acceptance_criteria", "criteria"):
        return (req.get("content") or {}).get("acceptance_criteria") or req.get("acceptance_criteria")
    if field in ("relationships", "links", "parent"):
        return req.get("relationships") if field != "parent" else req.get("parentId")
    return req.get(FIELD_ALIASES.get(field, field))


def _empty(v: Any) -> bool:
    return v in (None, "", [], {}) or v == "not_started"


def _matches(v: Any, wanted: str) -> bool:
    wanted = wanted.lower()
    if isinstance(v, (list, tuple, set)):
        return any(str(x).lower() == wanted for x in v)
    if isinstance(v, bool):
        return str(v).lower() == wanted
    return v is not None and str(v).lower() == wanted


def parse(query: str) -> Callable[[dict[str, Any]], bool]:
    try:
        tokens = shlex.split(query or "")
    except ValueError as exc:
        raise QueryError(f"Unbalanced quote in query: {exc}") from exc
    tests: list[Callable[[dict[str, Any]], bool]] = []
    for tok in tokens:
        negate = tok.startswith("-") and len(tok) > 1
        body = tok[1:] if negate else tok
        key, sep, val = body.partition(":")
        if sep and key and val:
            key = key.lower()
            if key == "no":
                test = (lambda f: lambda r: _empty(_value(r, f)))(val.lower())
            elif key == "has":
                test = (lambda f: lambda r: not _empty(_value(r, f)))(val.lower())
            else:
                test = (lambda f, w: lambda r: _matches(_value(r, f), w))(key, val)
        elif sep and key and not val:
            raise QueryError(f"'{tok}' has no value after the colon")
        else:
            needle = body.lower()
            test = (lambda n: lambda r: n in f"{r.get('title', '')} {(r.get('content') or {}).get('description', '')} {r.get('id', '')}".lower())(needle)
        tests.append((lambda t: lambda r: not t(r))(test) if negate else test)
    return lambda req: all(t(req) for t in tests)


def run(requirements: dict[str, dict], query: str) -> list[dict]:
    match = parse(query)
    return [r for r in requirements.values() if not r.get("deleted") and match(r)]
