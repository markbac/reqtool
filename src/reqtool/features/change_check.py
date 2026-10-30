"""
reqtool.features.change_check
=============================
``req check-changes``: the workflow rules the server enforces, checked on a branch's changes in CI (#351).

Without a server nothing stops someone editing YAML by hand, so a pull request is checked against its base:

- every status move recorded in an item's new history entries must be a transition its workflow allows, and
  together they must lead from the base status to the new one;
- the guards of the final state (required fields, acceptance criteria, child states) must be met by the item
  as it now is;
- a new item must start in its workflow's initial state.

Content hashes are ``req verify``'s job and signatures ``req validate``'s.
"""

from __future__ import annotations

from typing import Any

from reqtool.git_ops import run_git
from reqtool.identity import committed_copy, entries_since


def _finding(code: str, item: dict[str, Any], message: str) -> dict[str, str]:
    return {"code": code, "uid": item.get("uid", ""), "id": item.get("id", ""), "message": message}


def _allowed(store: Any, req_type: str, frm: str, to: str) -> bool:
    wf = store.get_workflow_for_type(req_type)
    table = wf.transitions if wf else store.config.workflow.transitions
    return to == frm or to in table.get(frm, [])


def _walk(store: Any, item: dict[str, Any], before: Any, steps: list[tuple]) -> tuple[str, str] | None:
    """The first problem on the way from ``before`` through ``steps`` to the item's status, or None.
    Guards can only be checked for the last step, against the item as it now is."""
    state, req_type = before, item.get("req_type", "functional")
    for i, (frm, to) in enumerate(steps):
        if frm != state:
            return "status_history_gap", f"history moves from '{frm}' but the item was in '{state}'"
        if not _allowed(store, req_type, frm, to):
            return "illegal_transition", f"'{frm}' to '{to}' is not a transition of the '{req_type}' workflow"
        if i == len(steps) - 1:
            problem = store.validate_transition({**item, "status": frm}, to)
            if problem:
                return "workflow_guard", problem
        state = to
    if state != item.get("status"):
        return "status_history_gap", f"history ends in '{state}' but the item is in '{item.get('status')}'"
    return None


def check_changes(store: Any, base_ref: str) -> list[dict[str, str]]:
    root = store.root
    rc, merge_base, err = run_git(["merge-base", base_ref, "HEAD"], root)
    if rc != 0:
        raise ValueError(f"Cannot compare with {base_ref}: {err}")
    rc, out, err = run_git(["diff", "--name-status", "--no-renames", merge_base, "HEAD", "--", "requirements"], root)
    if rc != 0:
        raise ValueError(err)
    findings = []
    for line in out.splitlines():
        status, _, rel = line.partition("\t")
        if not rel.endswith(".yaml") or status == "D":
            continue
        item = store.requirement_map().get(rel.rsplit("/", 1)[-1][:-5])
        if item is None or item.get("deleted"):
            continue
        wf = store.get_workflow_for_type(item.get("req_type", "functional"))
        initial = wf.initial if wf else store.config.workflow.initial
        base = committed_copy(root, root / rel, merge_base)
        if base is None:
            if item.get("status") != initial:
                findings.append(_finding("created_past_initial", item,
                                         f"new item starts in '{item.get('status')}', not '{initial}'"))
            continue
        before, after = base.get("status"), item.get("status")
        if before == after:
            continue
        steps = [(e.get("status_from"), e.get("status_to"))
                 for e in entries_since(base.get("history") or [], item.get("history") or []) if "status_to" in e]
        if not steps:
            steps = [(before, after)]   # edited without a history entry: check the move as one step
        problem = _walk(store, item, before, steps)
        if problem:
            findings.append(_finding(problem[0], item, problem[1]))
    return findings
