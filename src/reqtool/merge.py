"""
reqtool.merge
=============
A git merge driver for reqtool's YAML artefacts (#350).

Two people changing the same item on different branches always touch ``version``, ``content_hash``,
``last_modified`` and ``history``, so a plain text merge conflicts even when their edits do not overlap. This
driver merges field by field instead:

- each field is merged three ways; lists of records merge by identity (acceptance criteria by ``uid``,
  relationships by type and target, links by system and ref, attachments by file name) and nested blocks
  (``content``, ``approval`` ...) key by key, and ``tags`` as a set;
- ``history`` is the union of both sides, by date;
- ``version`` is the higher of the two, bumped once more (with a history entry) when the result differs from
  both sides; ``last_modified`` and ``content_hash`` are recomputed.

Fields both sides changed differently are left as ordinary git conflict markers around just those fields, and
the driver exits non-zero so git reports the conflict. Registered by ``req setup``:
``git config merge.reqtool.driver "req merge-file %O %A %B %P"`` with ``merge=reqtool`` in ``.gitattributes``.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from .fileio import (
    bump_version, compute_principle_hash, compute_requirement_hash, compute_tbd_hash, parse_semver, save_yaml,
    utcnow_iso, yaml_loads_safe,
)

ATTRIBUTES = ("requirements/*.yaml merge=reqtool", "principles/*.yaml merge=reqtool", "decisions/*.yaml merge=reqtool")
BOOKKEEPING = ("version", "content_hash", "last_modified", "history")
_HASH_BY_DIR: dict[str, Callable[[dict[str, Any]], str]] = {
    "requirements": compute_requirement_hash, "principles": compute_principle_hash, "decisions": compute_tbd_hash,
}
_LIST_KEYS: dict[str, Callable[[Any], Any]] = {
    "acceptance_criteria": lambda x: x.get("uid") or x.get("id"),
    "relationships": lambda x: (x.get("type"), (x.get("target") or {}).get("uid")),
    "links": lambda x: (x.get("system"), x.get("ref")),
    "attachments": lambda x: x.get("filename"),
}
_SETS = ("tags", "allocated_to")
_MISSING = object()


class _Conflict(Exception):
    pass


def _three_way(base: Any, ours: Any, theirs: Any) -> Any:
    if ours == theirs:
        return ours
    if ours == base:
        return theirs
    if theirs == base:
        return ours
    raise _Conflict()


def _merge_records(base: list, ours: list, theirs: list, key: Callable[[Any], Any]) -> list:
    """Lists of dicts matched by ``key``: order of ours, then theirs' additions; each record merged three ways."""
    if not all(isinstance(x, dict) for x in (*base, *ours, *theirs)):
        raise _Conflict()
    b, o, t = ({key(x): x for x in lst} for lst in (base, ours, theirs))
    out = []
    for k in [*o, *(k for k in t if k not in o)]:
        merged = _merge_value(b.get(k, _MISSING), o.get(k, _MISSING), t.get(k, _MISSING), None)
        if merged is not _MISSING:
            out.append(merged)
    return out


def _merge_set(base: list, ours: list, theirs: list) -> list:
    removed = (set(map(str, base)) - set(map(str, ours))) | (set(map(str, base)) - set(map(str, theirs)))
    out = []
    for x in [*ours, *theirs]:
        if str(x) not in removed and x not in out:
            out.append(x)
    return out


def _merge_value(base: Any, ours: Any, theirs: Any, field: Optional[str]) -> Any:
    try:
        return _three_way(base, ours, theirs)
    except _Conflict:
        pass
    lists = all(isinstance(x, list) for x in (ours, theirs)) and (base is _MISSING or isinstance(base, list))
    if lists and field in _SETS:
        return _merge_set(base if base is not _MISSING else [], ours, theirs)
    if lists and field in _LIST_KEYS:
        return _merge_records(base if base is not _MISSING else [], ours, theirs, _LIST_KEYS[field])
    if isinstance(ours, dict) and isinstance(theirs, dict) and (base is _MISSING or isinstance(base, dict)):
        b: dict = base if isinstance(base, dict) else {}
        out = {}
        for k in [*ours, *(k for k in theirs if k not in ours)]:
            merged = _merge_value(b.get(k, _MISSING), ours.get(k, _MISSING), theirs.get(k, _MISSING), k)
            if merged is not _MISSING:
                out[k] = merged
        return out
    raise _Conflict()


def _merge_history(*histories: list) -> list:
    seen, out = set(), []
    for entry in (e for h in histories for e in h):
        k = (entry.get("version"), entry.get("date"), entry.get("modified_by"), entry.get("summary"))
        if k not in seen:
            seen.add(k)
            out.append(entry)
    return sorted(out, key=lambda e: str(e.get("date") or ""))


def _higher(a: str, b: str) -> str:
    key = lambda v: tuple(parse_semver(v)[p] for p in ("major", "minor", "patch"))
    return a if key(a) >= key(b) else b


def merge_documents(base: dict, ours: dict, theirs: dict, hash_fn: Callable[[dict[str, Any]], str],
                    author: str, now: Optional[str] = None) -> tuple[dict, Optional[tuple[dict, dict, dict]]]:
    """Merge three versions of an artefact.

    Returns ``(merged, None)`` when the merge is clean. On a conflict it returns ``(ours, sides)``, where
    ``sides`` are the ours, base and theirs versions of the merge with each conflicting field taken from that
    side, so a text merge of the three puts markers around just those fields.
    """
    merged: dict[str, Any] = {}
    sides: tuple[dict[str, Any], dict[str, Any], dict[str, Any]] = ({}, {}, {})
    conflicts: list[str] = []
    for k in [*ours, *(k for k in theirs if k not in ours)]:
        if k in BOOKKEEPING:
            continue
        b, o, t = base.get(k, _MISSING), ours.get(k, _MISSING), theirs.get(k, _MISSING)
        try:
            value = _merge_value(b, o, t, k)
            if value is not _MISSING:
                for d in (merged, *sides):
                    d[k] = value
        except _Conflict:
            conflicts.append(k)
            for d, v in zip(sides, (o, b, t)):
                if v is not _MISSING:
                    d[k] = v
    version = _higher(str(ours.get("version") or "0.1.0"), str(theirs.get("version") or "0.1.0"))
    history = _merge_history(ours.get("history") or [], theirs.get("history") or [])
    def strip(d: dict) -> dict:
        return {k: v for k, v in d.items() if k not in BOOKKEEPING}
    changed_both = merged != strip(ours) and merged != strip(theirs)
    last_modified = max(str(ours.get("last_modified") or ""), str(theirs.get("last_modified") or ""))
    if changed_both and not conflicts:
        now = now or utcnow_iso()
        version = bump_version(version, "patch")
        last_modified = now
        history.append({"version": version, "date": now, "modified_by": author,
                        "summary": "Merged concurrent changes.", "commit_sha": None, "change_ref": None})
    if not conflicts:
        merged.update(version=version, last_modified=last_modified, history=history)
        merged["content_hash"] = hash_fn(merged)
        return merged, None
    # One hash for all three sides keeps the hash line out of the conflict; `req resolved` corrects it afterwards.
    content_hash = hash_fn(sides[0])
    for d in sides:
        d.update(version=version, last_modified=last_modified, history=history, content_hash=content_hash)
    return ours, sides


def _text_merge(ours: Path, base: Path, theirs: Path, labels: tuple[str, str, str]) -> int:
    """``git merge-file`` writes the result into ``ours``; returns the number of conflicts."""
    res = subprocess.run(["git", "merge-file", "-L", labels[0], "-L", labels[1], "-L", labels[2],
                          str(ours), str(base), str(theirs)], capture_output=True)
    return res.returncode


def merge_file(base_path: Path, ours_path: Path, theirs_path: Path, pathname: str = "", author: str = "reqtool") -> int:
    """Merge driver entry point: writes the result into ``ours_path``; returns 0 when clean, else non-zero."""
    labels = ("ours", "base", "theirs")
    texts = [p.read_text(encoding="utf-8") if p.exists() else "" for p in (base_path, ours_path, theirs_path)]
    docs = [yaml_loads_safe(t) if t.strip() else {} for t in texts]
    hash_fn = _HASH_BY_DIR.get(Path(pathname).parts[0] if pathname else "")
    if hash_fn is None or not all(isinstance(d, dict) for d in docs) or not docs[1] or not docs[2]:
        return _text_merge(ours_path, base_path, theirs_path, labels)
    merged, sides = merge_documents(docs[0], docs[1], docs[2], hash_fn, author)
    if sides is None:
        save_yaml(ours_path, merged)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        b, t = Path(tmp) / "base.yaml", Path(tmp) / "theirs.yaml"
        save_yaml(ours_path, sides[0])
        save_yaml(b, sides[1])
        save_yaml(t, sides[2])
        return _text_merge(ours_path, b, t, labels) or 1


def mark_resolved(root: Path, path: Path, author: str) -> dict[str, Any]:
    """After a conflict in ``path`` was resolved by hand: bump the version, record the resolution in history,
    recompute the hash and stage the file. Raises ValueError while conflict markers remain."""
    from .git_ops import stage_file
    from .fileio import load_yaml
    rel = path.resolve().relative_to(root.resolve())
    hash_fn = _HASH_BY_DIR.get(rel.parts[0])
    text = path.read_text(encoding="utf-8")
    if hash_fn is None:
        raise ValueError(f"{rel} is not a reqtool artefact")
    if any(line.startswith(("<<<<<<<", ">>>>>>>", "=======")) for line in text.splitlines()):
        raise ValueError(f"{rel} still has conflict markers")
    data = load_yaml(path)
    now = utcnow_iso()
    data["version"] = bump_version(str(data.get("version") or "0.1.0"), "patch")
    data["last_modified"] = now
    data["history"] = [*(data.get("history") or []), {
        "version": data["version"], "date": now, "modified_by": author, "summary": "Resolved merge conflict.",
        "commit_sha": None, "change_ref": None}]
    data["content_hash"] = hash_fn(data)
    save_yaml(path, data)
    stage_file(root, path.resolve())
    return {"path": str(rel), "version": data["version"]}


def install(root: Path, command: str, attributes: bool = True) -> bool:
    """Register the driver in this clone's git config and (with ``attributes``) declare it in ``.gitattributes``,
    which is committed so every clone uses it. Returns True when anything changed."""
    from .git_ops import run_git
    changed = False
    rc, current, _ = run_git(["config", "--local", "merge.reqtool.driver"], root)
    if rc != 0 or current.strip() != command:
        run_git(["config", "--local", "merge.reqtool.name", "reqtool YAML artefacts"], root)
        run_git(["config", "--local", "merge.reqtool.driver", command], root)
        changed = True
    missing = missing_attributes(root)
    if attributes and missing:
        attrs = root / ".gitattributes"
        lines = attrs.read_text(encoding="utf-8").splitlines() if attrs.exists() else []
        attrs.write_text("\n".join([*lines, "# reqtool merges its YAML field by field (req setup)", *missing]) + "\n",
                         encoding="utf-8")
        changed = True
    return changed


def missing_attributes(root: Path) -> list[str]:
    attrs = root / ".gitattributes"
    lines = attrs.read_text(encoding="utf-8").splitlines() if attrs.exists() else []
    return [a for a in ATTRIBUTES if a not in lines]


def is_installed(root: Path) -> bool:
    from .git_ops import run_git
    rc, out, _ = run_git(["config", "merge.reqtool.driver"], root)
    return rc == 0 and bool(out.strip())


def driver_command() -> str:
    """How git should run this installation's ``req merge-file``."""
    import sys
    exe = f'"{sys.executable}"' if " " in sys.executable else sys.executable
    prefix = exe if getattr(sys, "frozen", False) else f"{exe} -m reqtool"
    return f"{prefix} merge-file %O %A %B %P"
