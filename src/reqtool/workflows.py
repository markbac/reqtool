"""Workflow definitions: normalise them, check them, and draw them.

A workflow is a dict of ``initial``, ``states`` (id, label, colour, terminal), ``transitions`` (state to the
states it may move to) and ``guards`` (what must be true before an item may enter a state). Workflows live in
the repository's own ``.reqtool/hierarchy.yaml``, so a project can change them. This module has no web or file
code, so the editor, the CLI and the tests share it.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

STATE_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
WORKFLOW_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
FIELD_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
CHILDREN_ENFORCE = ("off", "warn", "error")
DEFAULT_COLOUR = "#8b949e"

# Fields a guard may require, offered by the editor. Any dotted path to a stored field is accepted.
KNOWN_FIELDS: dict[str, str] = {
    "title": "Title",
    "content.description": "Description",
    "content.rationale": "Rationale",
    "content.extended_description": "Extended description",
    "owner": "Owner",
    "assignee": "Assignee",
    "priority": "Priority",
    "domain": "Domain",
    "component": "Component",
    "iteration": "Iteration",
    "estimate": "Estimate",
    "verification_method": "Verification method",
    "safety_classification": "Safety classification",
    "source_document": "Source document",
    "target_release": "Target release",
}


def field_label(path: str) -> str:
    """A person-readable name for a field path."""
    return KNOWN_FIELDS.get(path) or path.split(".")[-1].replace("_", " ").capitalize()


def _plain(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


def normalise(data: Mapping[str, Any]) -> dict[str, Any]:
    """The definition in its full, explicit shape: every state has a transition list and every guard key.

    Writing everything out means a person editing the YAML can see each setting that exists.
    """
    states: list[dict[str, Any]] = []
    for raw in data.get("states") or []:
        s = _plain(raw)
        sid = str(s.get("id", "")).strip()
        states.append({
            "id": sid,
            "label": str(s.get("label") or sid).strip(),
            "colour": str(s.get("colour") or DEFAULT_COLOUR).strip(),
            "terminal": bool(s.get("terminal", False)),
        })
    ids = [s["id"] for s in states]
    transitions_in = data.get("transitions") or {}
    guards_in = data.get("guards") or {}
    transitions: dict[str, list[str]] = {}
    guards: dict[str, dict[str, Any]] = {}
    for sid in ids:
        targets = transitions_in.get(sid) or []
        seen: list[str] = []
        for t in targets:
            if t not in seen:
                seen.append(str(t))
        transitions[sid] = seen
        g = _plain(guards_in.get(sid) or {})
        guards[sid] = {
            "requires_fields": [str(f).strip() for f in (g.get("requires_fields") or []) if str(f).strip()],
            "requires_ac": bool(g.get("requires_ac", False)),
            "requires_children_in": [str(c).strip() for c in (g.get("requires_children_in") or []) if str(c).strip()],
            "children_enforce": str(g.get("children_enforce") or "warn").strip().lower(),
            "message": str(g.get("message") or ""),
        }
    # Transitions or guards that name an unknown state are kept so check() can report them.
    for sid, targets in transitions_in.items():
        if sid not in transitions:
            transitions[sid] = [str(t) for t in targets or []]
    for sid, g in guards_in.items():
        if sid not in guards:
            guards[sid] = _plain(g) or {}
    return {"initial": str(data.get("initial") or (ids[0] if ids else "")).strip(),
            "states": states, "transitions": transitions, "guards": guards}


def check(data: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """``(errors, warnings)`` for a definition. Errors stop it being saved; warnings are for the editor to show."""
    wf = normalise(data)
    errors: list[str] = []
    warnings: list[str] = []
    ids = [s["id"] for s in wf["states"]]
    if not ids:
        return ["A workflow needs at least one state"], warnings
    for sid in ids:
        if not STATE_ID.match(sid):
            errors.append(f"State id '{sid}' must be lower case letters, digits and underscores, starting with a letter")
    if len(set(ids)) != len(ids):
        errors.append("State ids must be unique")
    for s in wf["states"]:
        if not COLOUR.match(s["colour"]):
            errors.append(f"State '{s['id']}' has colour '{s['colour']}': use a hex colour such as #1f6feb")
    if wf["initial"] not in ids:
        errors.append(f"The initial state '{wf['initial']}' is not one of the states")
    known = set(ids)
    for src, targets in wf["transitions"].items():
        if src not in known:
            errors.append(f"Transitions are defined from an unknown state '{src}'")
        for t in targets:
            if t not in known:
                errors.append(f"'{src}' can move to an unknown state '{t}'")
            elif t == src:
                warnings.append(f"'{src}' lists itself as a target: staying in a state needs no transition")
    for sid, g in wf["guards"].items():
        if sid not in known:
            errors.append(f"A guard is defined on an unknown state '{sid}'")
            continue
        for f in g.get("requires_fields", []):
            if not FIELD_PATH.match(f):
                errors.append(f"Guard on '{sid}': '{f}' is not a field path such as content.rationale")
        if g.get("children_enforce") not in CHILDREN_ENFORCE:
            errors.append(f"Guard on '{sid}': children_enforce must be one of {', '.join(CHILDREN_ENFORCE)}")
    terminal = {s["id"] for s in wf["states"] if s["terminal"]}
    if wf["initial"] in known and not errors:
        reach, stack = set(), [wf["initial"]]
        while stack:
            cur = stack.pop()
            if cur in reach:
                continue
            reach.add(cur)
            stack.extend(wf["transitions"].get(cur, []))
        for sid in ids:
            if sid not in reach:
                warnings.append(f"State '{sid}' can never be reached from '{wf['initial']}'")
        if terminal:
            for sid in ids:
                seen, stack = set(), [sid]
                while stack:
                    cur = stack.pop()
                    if cur in seen:
                        continue
                    seen.add(cur)
                    stack.extend(wf["transitions"].get(cur, []))
                if not (seen & terminal):
                    warnings.append(f"State '{sid}' can never reach a terminal state")
    return errors, warnings


# --- Mermaid ------------------------------------------------------------------------------------

_LABEL_UNSAFE = re.compile(r"[^A-Za-z0-9 ,.:/()'_+-]")


def _text(value: str, limit: int = 60) -> str:
    """Text safe inside a Mermaid label: no quotes, semicolons, brackets or markup."""
    out = _LABEL_UNSAFE.sub("", str(value).replace('"', "'").replace(";", ","))
    out = " ".join(out.split())
    return out[:limit] or "-"


def guard_summary(guard: Mapping[str, Any]) -> str:
    """A short phrase for what entering a state needs, or '' when it needs nothing."""
    parts = [field_label(f).lower() for f in guard.get("requires_fields") or []]
    if guard.get("requires_ac"):
        parts.append("acceptance criteria")
    if guard.get("requires_children_in") and guard.get("children_enforce", "warn") != "off":
        parts.append("children " + "/".join(guard["requires_children_in"]))
    return ("needs " + ", ".join(parts)) if parts else ""


def to_mermaid(data: Mapping[str, Any]) -> str:
    """The workflow as Mermaid flowchart text. It contains no semicolons, which break some renderers."""
    wf = normalise(data)
    lines = ["flowchart LR"]
    states = {s["id"]: s for s in wf["states"]}
    if not states:
        return "\n".join(lines + ['    empty["No states"]'])
    # Node ids are prefixed because words such as "end" are reserved in Mermaid.
    for sid, s in states.items():
        label = _text(s["label"])
        shape = f'(["{label}"])' if s["terminal"] else f'["{label}"]'
        lines.append(f"    s_{sid}{shape}")
    lines.append('    start_(("start"))')
    if wf["initial"] in states:
        lines.append(f"    start_ --> s_{wf['initial']}")
    for src, targets in wf["transitions"].items():
        if src not in states:
            continue
        for t in targets:
            if t not in states:
                continue
            need = guard_summary(wf["guards"].get(t, {}))
            arrow = f'-->|"{_text(need, 100)}"|' if need else "-->"
            lines.append(f"    s_{src} {arrow} s_{t}")
    for sid, s in states.items():
        colour = s["colour"] if COLOUR.match(s["colour"]) else DEFAULT_COLOUR
        lines.append(f"    style s_{sid} fill:{colour}33,stroke:{colour},color:#e6edf3")
    lines.append("    style start_ fill:#30363d,stroke:#8b949e,color:#e6edf3")
    return "\n".join(lines)
