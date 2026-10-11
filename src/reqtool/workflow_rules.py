"""Parent and child rules: checks up and down the tree, and automatic (or suggested) roll-up of status.

Pure functions over the hierarchy config and the requirements map. Nothing here reads or writes a file; the
requirement service applies what this module works out. See "Parent and child rules" in docs/USER_GUIDE.md.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Iterable, Mapping, Optional

from reqtool.models import HierarchyConfig, HierarchyWorkflowDef, ParentChildRule
from reqtool.models.config import OVERRIDE_LEVELS, RULE_KINDS
from reqtool.stores.hierarchy_store import get_workflow_for_type

CHECK_KINDS = ("up", "down")
CHANGE_KINDS = ("start", "complete", "reopen", "cancel")
CHECK_MODES = ("off", "warn", "error")
CHANGE_MODES = ("off", "suggest", "auto")
SCOPES = {"up": ("parent", "ancestors"), "start": ("parent", "ancestors"), "reopen": ("parent", "ancestors"),
          "down": ("children", "descendants"), "complete": ("children", "descendants"),
          "cancel": ("children", "descendants")}
MAX_DEPTH = 25
_CANCELLED = {"cancelled", "canceled", "deprecated", "rejected", "obsolete", "withdrawn",
              "user_error", "duplicate", "not_reproducible"}
_LEVEL_WORDS = {1: "one level", 2: "two levels", 3: "three levels", 4: "four levels", 5: "five levels"}

Requirements = Mapping[str, dict[str, Any]]
Validate = Callable[[dict[str, Any], str], Optional[str]]


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

def _wf(hierarchy: HierarchyConfig, item: dict[str, Any]) -> Optional[HierarchyWorkflowDef]:
    return get_workflow_for_type(hierarchy, item.get("req_type", "functional"))


def resolve_states(tokens: Iterable[str], wf: Optional[HierarchyWorkflowDef]) -> list[str]:
    """State ids, in order, for state ids and ``@tokens``. An id the workflow does not have is kept as written."""
    if wf is None:
        return [t for t in tokens if not t.startswith("@")]
    ids = [s.id for s in wf.states]
    terminal = [s.id for s in wf.states if s.terminal]
    named = {
        "@initial": [wf.initial],
        "@terminal": terminal,
        "@cancelled": [i for i in terminal if i in _CANCELLED],
        "@done": [i for i in terminal if i not in _CANCELLED],
        "@started": [i for i in ids if i != wf.initial and i not in terminal],
    }
    out: list[str] = []
    for tok in tokens:
        for sid in (named.get(tok, []) if tok.startswith("@") else [tok]):
            if sid not in out:
                out.append(sid)
    return out


def pick_target(wf: Optional[HierarchyWorkflowDef], current: str, tokens: Iterable[str]) -> Optional[str]:
    """First state in ``tokens`` the workflow lets an item in ``current`` move straight to."""
    if wf is None:
        return None
    allowed = wf.transitions.get(current, [])
    for sid in resolve_states(tokens, wf):
        if sid in allowed:
            return sid
    return None


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------

def _live(r: dict[str, Any]) -> bool:
    return not r.get("deleted")


def children_index(reqs: Requirements) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for uid, r in reqs.items():
        if _live(r) and r.get("parentId"):
            index.setdefault(r["parentId"], []).append(uid)
    return index


def ancestors(reqs: Requirements, uid: str) -> list[tuple[int, dict[str, Any]]]:
    """(distance, item) from the parent upwards. Stops at a missing parent or a loop."""
    out: list[tuple[int, dict[str, Any]]] = []
    seen = {uid}
    cur = reqs.get(uid, {}).get("parentId")
    dist = 1
    while cur and cur not in seen and cur in reqs and dist <= MAX_DEPTH:
        seen.add(cur)
        out.append((dist, reqs[cur]))
        cur = reqs[cur].get("parentId")
        dist += 1
    return out


def descendants(reqs: Requirements, index: dict[str, list[str]], uid: str,
                direct_only: bool = False) -> list[tuple[int, dict[str, Any]]]:
    out: list[tuple[int, dict[str, Any]]] = []
    seen = {uid}
    queue = deque((c, 1) for c in index.get(uid, []))
    while queue:
        cur, dist = queue.popleft()
        if cur in seen or dist > MAX_DEPTH:
            continue
        seen.add(cur)
        out.append((dist, reqs[cur]))
        if not direct_only:
            queue.extend((c, dist + 1) for c in index.get(cur, []))
    return out


def _matches(types: list[str], item: dict[str, Any]) -> bool:
    return "*" in types or item.get("req_type") in types


def _reach(rule: ParentChildRule, dist: int) -> bool:
    if rule.scope in ("parent", "children"):
        return dist == 1
    return rule.levels is None or dist <= rule.levels


def _ref(item: dict[str, Any]) -> str:
    return f"{item.get('req_type', 'item')} {item.get('id') or item.get('uid')}"


def _where(dist: int, up: bool) -> str:
    if dist == 1:
        return "its parent" if up else "a child"
    words = _LEVEL_WORDS.get(dist, f"{dist} levels")
    return f"{words} {'up' if up else 'down'}"


def rule_label(rule: ParentChildRule) -> str:
    return rule.label or rule.id


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_move(hierarchy: HierarchyConfig, reqs: Requirements, req: dict[str, Any], to_state: str,
               allow_same: bool = False) -> list[dict[str, Any]]:
    """Findings for moving ``req`` to ``to_state``: upward checks on its ancestors, downward on its descendants.

    Each finding is ``{rule, label, kind, mode, message, items, override}``. Rules that are off give nothing.
    """
    findings: list[dict[str, Any]] = []
    if not hierarchy.rules.rules or (to_state == req.get("status") and not allow_same):
        return findings
    own_wf = _wf(hierarchy, req)
    uid = req.get("uid", "")
    index = children_index(reqs)
    for rule in hierarchy.rules.rules:
        if rule.mode not in ("warn", "error") or rule.kind not in CHECK_KINDS:
            continue
        if rule.kind == "up" and _matches(rule.child_types, req):
            if to_state not in resolve_states(rule.to or ["@started"], own_wf):
                continue
            for dist, anc in ancestors(reqs, uid):
                if not _reach(rule, dist) or not _matches(rule.parent_types, anc) or not _live(anc):
                    continue
                if anc.get("status") in resolve_states(rule.when_in or ["@terminal"], _wf(hierarchy, anc)):
                    findings.append(_finding(rule, [anc], (
                        f"{_ref(anc)}, {_where(dist, True)}, is '{anc.get('status')}', so "
                        f"{_ref(req)} cannot move to '{to_state}'")))
        elif rule.kind == "down" and _matches(rule.parent_types, req):
            if to_state not in resolve_states(rule.to or ["@terminal"], own_wf):
                continue
            blockers = []
            for dist, child in descendants(reqs, index, uid, rule.scope == "children"):
                if not _reach(rule, dist) or not _matches(rule.child_types, child):
                    continue
                if child.get("status") not in resolve_states(rule.children_in or ["@terminal"], _wf(hierarchy, child)):
                    blockers.append((dist, child))
            if blockers:
                names = ", ".join(f"{_ref(c)} ({c.get('status')}, {_where(d, False)})" for d, c in blockers[:6])
                more = f" and {len(blockers) - 6} more" if len(blockers) > 6 else ""
                findings.append(_finding(rule, [c for _d, c in blockers], (
                    f"{_ref(req)} cannot move to '{to_state}' while these are not finished: {names}{more}")))
    return findings


def audit(hierarchy: HierarchyConfig, reqs: Requirements) -> list[dict[str, Any]]:
    """Items that break a check now, whatever moved them there. A forced item is reported as forced, not as a failure."""
    out = []
    for uid, req in reqs.items():
        if not _live(req):
            continue
        found = check_move(hierarchy, reqs, req, req.get("status", ""), allow_same=True)
        for f in found:
            # `down` rules judge a move into a state; auditing asks whether the item sits in one with open children.
            out.append({**f, "uid": uid, "id": req.get("id"), "forced": _was_forced(req)})
    return out


def _finding(rule: ParentChildRule, items: list[dict[str, Any]], message: str) -> dict[str, Any]:
    return {"rule": rule.id, "label": rule_label(rule), "kind": rule.kind, "mode": rule.mode, "message": message,
            "items": [i.get("id") or i.get("uid") for i in items], "override": rule.override}


# ---------------------------------------------------------------------------
# Roll-up
# ---------------------------------------------------------------------------

def _was_forced(item: dict[str, Any]) -> bool:
    mark = (item.get("attributes") or {}).get("forced")
    return isinstance(mark, dict) and mark.get("status") == item.get("status")


def _is_terminal(hierarchy: HierarchyConfig, item: dict[str, Any], status: Optional[str] = None) -> bool:
    return (status or item.get("status")) in resolve_states(["@terminal"], _wf(hierarchy, item))


def _is_started(hierarchy: HierarchyConfig, item: dict[str, Any], status: Optional[str]) -> bool:
    return status in resolve_states(["@started"], _wf(hierarchy, item))


def _triggered(hierarchy: HierarchyConfig, reqs: Requirements, index: dict[str, list[str]], rule: ParentChildRule,
               uid: str, old: Optional[str], new: str) -> list[dict[str, Any]]:
    """Items ``rule`` wants to move because ``uid`` went from ``old`` to ``new``."""
    item = reqs[uid]
    hits: list[dict[str, Any]] = []
    if rule.kind in ("start", "complete", "reopen") and _matches(rule.child_types, item):
        for dist, anc in ancestors(reqs, uid):
            if not _reach(rule, dist) or not _matches(rule.parent_types, anc):
                continue
            status = anc.get("status")
            awf = _wf(hierarchy, anc)
            if rule.kind == "start":
                if _is_started(hierarchy, item, new) and status in resolve_states(rule.when_in or ["@initial"], awf):
                    hits.append(anc)
            elif rule.kind == "reopen":
                reopened = old is None or _is_terminal(hierarchy, item, old)
                if reopened and not _is_terminal(hierarchy, item, new) and \
                        status in resolve_states(rule.when_in or ["@terminal"], awf):
                    hits.append(anc)
            elif rule.kind == "complete" and dist == 1 and _is_terminal(hierarchy, item, new):
                if _is_terminal(hierarchy, anc):
                    continue
                found = descendants(reqs, index, anc["uid"], rule.scope == "children")
                kids = [c for d, c in found if _reach(rule, d) and _matches(rule.child_types, c)]
                if kids and all(c.get("status") in resolve_states(rule.children_in or ["@terminal"], _wf(hierarchy, c))
                                for c in kids):
                    hits.append(anc)
    elif rule.kind == "cancel" and _matches(rule.parent_types, item):
        if new in resolve_states(rule.when_in or ["@cancelled"], _wf(hierarchy, item)):
            for dist, child in descendants(reqs, index, uid, rule.scope == "children"):
                if _reach(rule, dist) and _matches(rule.child_types, child) and not _is_terminal(hierarchy, child):
                    hits.append(child)
    return hits


_DEFAULT_TARGETS = {
    "start": ["in_progress", "active", "@started"],
    "reopen": ["in_progress", "active", "@started"],
    "complete": ["done", "approved", "@done"],
    "cancel": ["@cancelled"],
}


def plan_rollups(hierarchy: HierarchyConfig, reqs: Requirements, uid: str, old: Optional[str], new: str,
                 validate: Validate) -> dict[str, list[dict[str, Any]]]:
    """What the roll-up rules do after ``uid`` moved from ``old`` to ``new``.

    Returns ``{"auto": [...], "suggest": [...], "blocked": [...]}``. An ``auto`` entry has already been checked
    with ``validate`` and can be applied in order. A move that the parent's workflow or guards refuse goes to
    ``blocked`` with the reason, so a child's save never fails because of its parent. Chains (story, feature, epic)
    are followed through ``auto`` moves; loops and depth are bounded.
    """
    out: dict[str, list[dict[str, Any]]] = {"auto": [], "suggest": [], "blocked": []}
    rules = [r for r in hierarchy.rules.rules if r.kind in CHANGE_KINDS and r.mode in ("suggest", "auto")]
    if not rules or uid not in reqs:
        return out
    sim: dict[str, dict[str, Any]] = dict(reqs)
    sim[uid] = {**reqs[uid], "status": new}
    queue: deque[tuple[str, Optional[str], str, int]] = deque([(uid, old, new, 0)])
    seen: set[tuple[str, str]] = set()
    while queue:
        cur, was, now, depth = queue.popleft()
        if depth >= MAX_DEPTH or (cur, now) in seen:
            continue
        seen.add((cur, now))
        index = children_index(sim)
        for rule in rules:
            for target in _triggered(hierarchy, sim, index, rule, cur, was, now):
                tuid = target["uid"]
                if _was_forced(target) and not rule.reapply:
                    continue
                twf = _wf(hierarchy, target)
                to = pick_target(twf, target.get("status", ""), rule.to or _DEFAULT_TARGETS[rule.kind])
                entry = {"uid": tuid, "id": target.get("id"), "from": target.get("status"), "to": to,
                         "rule": rule.id, "label": rule_label(rule), "kind": rule.kind, "mode": rule.mode,
                         "because": sim[cur].get("id") or cur}
                if to is None:
                    entry["reason"] = f"{target.get('status')} has no direct move to {'/'.join(rule.to or _DEFAULT_TARGETS[rule.kind])}"
                    out["blocked"].append(entry)
                    continue
                problem = validate(target, to)
                if problem:
                    entry["reason"] = problem
                    out["blocked"].append(entry)
                    continue
                if rule.mode == "suggest":
                    out["suggest"].append(entry)
                    continue
                out["auto"].append(entry)
                sim[tuid] = {**target, "status": to}
                queue.append((tuid, target.get("status"), to, depth + 1))
    return out


# ---------------------------------------------------------------------------
# Override
# ---------------------------------------------------------------------------

def may_override(hierarchy: HierarchyConfig, finding: dict[str, Any], role: Optional[str]) -> bool:
    from reqtool.permissions import role_rank
    level = finding.get("override") or hierarchy.rules.override
    if level == "none":
        return False
    return role_rank(role) >= role_rank(level)


# ---------------------------------------------------------------------------
# Validation of the configuration
# ---------------------------------------------------------------------------

def check_config(hierarchy: HierarchyConfig) -> list[str]:
    """Problems in the rule set: bad kinds, modes, scopes, and types or states the repository does not have."""
    problems: list[str] = []
    if hierarchy.rules.override not in OVERRIDE_LEVELS:
        problems.append(f"rules.override must be one of {', '.join(OVERRIDE_LEVELS)}")
    seen: set[str] = set()
    all_states = {s.id for wf in hierarchy.workflows.values() for s in wf.states}
    for rule in hierarchy.rules.rules:
        at = f"Rule '{rule.id}'"
        if rule.id in seen:
            problems.append(f"{at}: the id is used twice")
        seen.add(rule.id)
        if rule.kind not in RULE_KINDS:
            problems.append(f"{at}: kind must be one of {', '.join(RULE_KINDS)}")
            continue
        modes = CHECK_MODES if rule.kind in CHECK_KINDS else CHANGE_MODES
        if rule.mode not in modes:
            problems.append(f"{at}: mode must be one of {', '.join(modes)} for a '{rule.kind}' rule")
        if rule.scope not in SCOPES[rule.kind]:
            problems.append(f"{at}: scope must be one of {', '.join(SCOPES[rule.kind])} for a '{rule.kind}' rule")
        if rule.override is not None and rule.override not in OVERRIDE_LEVELS:
            problems.append(f"{at}: override must be one of {', '.join(OVERRIDE_LEVELS)}")
        for field in ("parent_types", "child_types"):
            for t in getattr(rule, field):
                if t != "*" and t not in hierarchy.types:
                    problems.append(f"{at}: {field} names the unknown type '{t}'")
        for field in ("when_in", "to", "children_in"):
            for sid in getattr(rule, field):
                if not sid.startswith("@") and sid not in all_states:
                    problems.append(f"{at}: {field} names the unknown state '{sid}'")
                elif sid.startswith("@") and sid not in ("@initial", "@started", "@terminal", "@done", "@cancelled"):
                    problems.append(f"{at}: {field} uses the unknown token '{sid}'")
    return problems


def default_rules(mode_checks: str = "warn", mode_changes: str = "suggest") -> dict[str, Any]:
    """The rule set new repositories start with: checks warn, roll-ups are suggested."""
    return {"override": "editor", "rules": [
        {"id": "no-start-under-closed", "kind": "up", "label": "No work under a closed parent", "scope": "ancestors",
         "mode": mode_checks, "to": ["@started"], "when_in": ["@terminal"]},
        {"id": "finish-children-first", "kind": "down", "label": "Finish children before the parent",
         "scope": "descendants", "mode": mode_checks, "to": ["@terminal"], "children_in": ["@terminal"]},
        {"id": "rollup-start", "kind": "start", "label": "Roll up: started", "mode": mode_changes},
        {"id": "rollup-complete", "kind": "complete", "label": "Roll up: complete", "scope": "children",
         "mode": mode_changes},
        {"id": "rollup-reopen", "kind": "reopen", "label": "Roll up: reopened", "mode": mode_changes},
        {"id": "cascade-cancel", "kind": "cancel", "label": "Cancel children with the parent", "scope": "descendants",
         "mode": "off"},
    ]}
