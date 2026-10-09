"""
reqtool.features.insight
========================
Read-only views over the requirement graph: traceability, lifecycle blockers, product overview,
roadmap, impact preview and the release readiness gate (ENH-01/02/03/06, FEAT-01/03).
"""

from __future__ import annotations

from typing import Any, Optional

from reqtool.graph import relationship_target

VERIFIED = ("passed", "verified")
DONE_STATUSES = ("done", "closed", "approved", "deprecated", "cancelled")
STRATEGIC = ("theme", "initiative", "epic")
# A requirement is "approved or later" once it has passed review.
APPROVED_STATES = ("approved", "baselined", "verified")


def _live(store) -> dict[str, dict]:
    return {u: r for u, r in store.requirement_map().items() if not r.get("deleted")}


def _ref(r: dict) -> dict:
    return {"uid": r["uid"], "id": r.get("id"), "title": r.get("title", ""), "status": r.get("status"),
            "req_type": r.get("req_type")}


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def is_verified(req: dict) -> bool:
    return (req.get("verification") or {}).get("status") in VERIFIED


# --- ENH-01 traceability --------------------------------------------------------

def requirement_trace(store, uid: str) -> Optional[dict[str, Any]]:
    """Upstream and downstream links of one requirement, its gaps and coverage percentages."""
    live = _live(store)
    req = live.get(uid)
    if req is None:
        return None
    graph = store.graph
    upstream = []
    for rel in req.get("relationships") or []:
        target = relationship_target(rel)
        if target and target in live:
            upstream.append({**_ref(live[target]), "relationship": rel.get("type", ""), "suspect": bool(rel.get("suspect"))})
    downstream = []
    for src, rel_type in graph.incoming.get(uid, []):
        if src in live:
            downstream.append({**_ref(live[src]), "relationship": rel_type})
    children = [_ref(live[c]) for c in graph.children.get(uid, []) if c in live]
    gaps = []
    if not upstream and not req.get("parentId"):
        gaps.append("no_upstream")
    if not downstream and not children:
        gaps.append("no_downstream")
    if not is_verified(req):
        gaps.append("not_verified")
    covered_children = sum(1 for c in children if is_verified(live[c["uid"]]))
    return {
        "uid": uid, "id": req.get("id"), "upstream": upstream, "downstream": downstream, "children": children,
        "gaps": gaps,
        "coverage": {
            "downstream_traced_pct": _pct(1 if (downstream or children) else 0, 1),
            "children_verified_pct": _pct(covered_children, len(children)),
        },
    }


# --- ENH-02 lifecycle -------------------------------------------------------------

LIFECYCLE = ("draft", "review", "approved", "verified", "baselined")


def lifecycle(store, uid: str) -> Optional[dict[str, Any]]:
    """Where the requirement is on the draft to baselined strip, and what blocks the next step."""
    live = _live(store)
    req = live.get(uid)
    if req is None:
        return None
    status = req.get("status", "draft")
    stage = "draft"
    if status in ("in_review", "reviewed", "review"):
        stage = "review"
    if status == "approved":
        stage = "approved"
    if status == "approved" and is_verified(req):
        stage = "verified"
    baselined = _baselined_uids(store).get(uid, [])
    if stage == "verified" and baselined:
        stage = "baselined"
    blockers = []
    for tbd in store.open_tbds_for(req):
        blockers.append({"code": "open_tbd", "message": f"Open TBD {tbd}"})
    if not is_verified(req) and status in APPROVED_STATES:
        blockers.append({"code": "not_verified", "message": "Verification has not passed"})
    trace = requirement_trace(store, uid)
    if trace and "no_upstream" in trace["gaps"] and req.get("req_type") not in STRATEGIC:
        blockers.append({"code": "trace_gap", "message": "No upstream parent or link"})
    for rel in req.get("relationships") or []:
        if rel.get("suspect"):
            blockers.append({"code": "suspect_link", "message": f"Suspect link ({rel.get('type', '')})"})
    return {"uid": uid, "stages": list(LIFECYCLE), "stage": stage, "blockers": blockers,
            "baselines": baselined}


def _baselined_uids(store) -> dict[str, list[str]]:
    """uid -> baseline names whose tagged tree contains the requirement file (empty without git)."""
    from reqtool.git_ops import git_list_tags, is_git_repo, run_git
    out: dict[str, list[str]] = {}
    if not is_git_repo(store.root):
        return out
    for tag in git_list_tags(store.root, prefix="baseline/"):
        code, listing, _ = run_git(["ls-tree", "-r", "--name-only", tag["name"], "--", "requirements"], store.root)
        if code != 0:
            continue
        for path in listing.splitlines():
            if path.endswith(".yaml"):
                uid = path.rsplit("/", 1)[-1][:-5]
                out.setdefault(uid, []).append(tag["name"])
    return out


# --- ENH-03 overview --------------------------------------------------------------

def overview(store, product_id: Optional[str] = None) -> dict[str, Any]:
    reqs = store.resolved_requirements(product_id) if product_id else store.requirement_map()
    live = [r for r in reqs.values() if not r.get("deleted")]
    total = len(live)
    approved = sum(1 for r in live if r.get("status") in APPROVED_STATES)
    verified = sum(1 for r in live if is_verified(r))
    traced = sum(1 for r in live if (r.get("relationships") or r.get("parentId")))
    by_status: dict[str, int] = {}
    for r in live:
        by_status[r.get("status", "draft")] = by_status.get(r.get("status", "draft"), 0) + 1
    from reqtool.validation import validate_all
    result = validate_all(store)
    return {
        "product": product_id,
        "counts": {"requirements": total, "modules": len(store.module_map()), "products": len(store.product_map()),
                   "open_tbds": sum(1 for t in store.live_tbds() if t.get("status") in ("open", "in_progress")),
                   "decisions": len(store.live_decision_records())},
        "by_status": by_status,
        "percentages": {"approved": _pct(approved, total), "verified": _pct(verified, total),
                        "traced": _pct(traced, total)},
        "validation": {"errors": len(result.get("errors", [])), "warnings": len(result.get("warnings", []))},
        "baselines": sorted(_baseline_names(store)),
    }


def _baseline_names(store) -> list[str]:
    from reqtool.git_ops import git_list_tags, is_git_repo
    if not is_git_repo(store.root):
        return []
    return [t["name"] for t in git_list_tags(store.root, prefix="baseline/")]


# --- ENH-06 roadmap ---------------------------------------------------------------

def roadmap(store) -> list[dict[str, Any]]:
    """Theme -> Initiative -> Epic tree with status, target release and a health flag."""
    live = _live(store)
    graph = store.graph

    def node(uid: str) -> dict[str, Any]:
        r = live[uid]
        kids = [node(c) for c in graph.children.get(uid, []) if c in live and live[c].get("req_type") in STRATEGIC]
        leaves = [live[d] for d in graph.descendants(uid) if live[d].get("req_type") not in STRATEGIC]
        done = sum(1 for x in leaves if x.get("status") in DONE_STATUSES)
        blocked = sum(1 for x in leaves for rel in x.get("relationships") or [] if rel.get("suspect"))
        health = "grey" if not leaves else ("red" if blocked else ("green" if done == len(leaves) else "amber"))
        return {**_ref(r), "target_release": r.get("target_release") or r.get("release"),
                "progress_pct": _pct(done, len(leaves)), "children_count": len(leaves),
                "health": health, "children": kids}

    roots = [u for u, r in live.items() if r.get("req_type") in STRATEGIC
             and (not r.get("parentId") or live.get(r["parentId"], {}).get("req_type") not in STRATEGIC)]
    return [node(u) for u in sorted(roots, key=lambda u: live[u].get("id") or u)]


# --- FEAT-03 impact preview ---------------------------------------------------------

def impact_preview(store, uid: str, proposed: dict[str, Any]) -> Optional[dict[str, Any]]:
    """What saving ``proposed`` would do: changed fields, items that go suspect, baselines touched."""
    from reqtool.fileio import compute_requirement_hash
    live = _live(store)
    current = live.get(uid)
    if current is None:
        return None
    merged = {**current, **{k: v for k, v in proposed.items() if v is not None}}
    if isinstance(proposed.get("content"), dict):
        merged["content"] = {**(current.get("content") or {}), **proposed["content"]}
    changed = sorted(k for k in proposed if proposed[k] is not None and current.get(k) != merged.get(k))
    content_changes = compute_requirement_hash(merged) != compute_requirement_hash(current)
    suspect = []
    if content_changes:
        for src, rel_type in store.graph.suspect_closure(uid):
            if src in live:
                suspect.append({**_ref(live[src]), "relationship": rel_type})
    return {"uid": uid, "changed_fields": changed, "content_changed": content_changes,
            "would_become_suspect": suspect, "affects_baselines": _baselined_uids(store).get(uid, []),
            "open_tbds": store.open_tbds_for(current)}


# --- FEAT-01 readiness gate ---------------------------------------------------------

def release_readiness(store, product_id: Optional[str] = None) -> dict[str, Any]:
    """Policy findings that should stop a release. ``ready`` is true when there are none."""
    from reqtool.git_ops import dirty_paths, is_git_repo
    reqs = store.resolved_requirements(product_id) if product_id else store.requirement_map()
    findings: list[dict[str, str]] = []

    def add(code: str, req: dict, message: str) -> None:
        findings.append({"code": code, "uid": req["uid"], "id": req.get("id") or req["uid"], "message": message})

    for r in (r for r in reqs.values() if not r.get("deleted")):
        approved = r.get("status") in APPROVED_STATES
        if approved:
            for tbd in store.open_tbds_for(r):
                add("open_tbd_on_approved", r, f"Approved item has open TBD {tbd}")
        if r.get("safety_related") and not is_verified(r):
            add("unverified_safety", r, "Safety-related item is not verified")
        for rel in r.get("relationships") or []:
            if rel.get("suspect"):
                add("suspect_link", r, f"Suspect {rel.get('type', '')} link needs review")
        if approved and not (r.get("relationships") or r.get("parentId")) and r.get("req_type") not in STRATEGIC:
            add("trace_gap", r, "Approved item has no parent or traceability link")
    if is_git_repo(store.root):
        dirty = dirty_paths(store.root, ("requirements", "principles", "decisions", "modules", "products"))
        for path in dirty:
            findings.append({"code": "dirty_baseline", "uid": "", "id": path,
                             "message": f"Uncommitted change would not be in a baseline: {path}"})
    return {"ready": not findings, "count": len(findings), "findings": findings}


# --- MOD-10 strategic summary ---------------------------------------------------------

def strategic_summary(store, uid: str) -> Optional[dict[str, Any]]:
    """Roll-up for a Theme, Initiative or Epic: child counts, completion, estimate, open TBDs, validation."""
    from reqtool.validation import validate_all
    live = _live(store)
    req = live.get(uid)
    if req is None:
        return None
    members = [uid, *[d for d in store.graph.descendants(uid) if d in live]]
    below = [live[m] for m in members[1:]]
    by_type: dict[str, dict[str, int]] = {}
    for r in below:
        counts = by_type.setdefault(r.get("req_type", "functional"), {})
        counts[r.get("status", "draft")] = counts.get(r.get("status", "draft"), 0) + 1
    progress = store.compute_progress_rollup(uid)
    open_tbds = sorted({t for m in members for t in store.open_tbds_for(live[m])})
    scope = set(members)
    result = validate_all(store)
    errors = [e for e in result.get("errors", []) if e.get("uid") in scope]
    warnings = [w for w in result.get("warnings", []) if w.get("uid") in scope]
    return {
        "uid": uid, "id": req.get("id"), "req_type": req.get("req_type"),
        "children": len(store.graph.children.get(uid, [])), "descendants": len(below),
        "by_type": by_type,
        "progress_pct": progress.get("progress_pct", 0.0), "total_estimate": progress.get("total_estimate", 0.0),
        "done_estimate": progress.get("done_estimate", 0.0), "open_tbds": open_tbds,
        "validation": {"errors": len(errors), "warnings": len(warnings), "ok": not errors},
    }
