"""
reqtool.features.visuals
========================
Data for the Views panel: the item hierarchy, the allowed type structure, coverage, impact, flow through the
workflow, burn-up, decision ageing, the principle heatmap and the traceability grid. Every function reads the
store and returns plain data, so the same numbers back the screen, a CSV and a test. Sizes are capped and the
result says how many were shown out of how many exist.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from reqtool.graph import relationship_target
from reqtool.stores.hierarchy_store import get_workflow_for_type
from reqtool.workflows import _text

DEFAULT_COLOUR = "#8b949e"
NODE_CAP = 400
GRAPH_CAP = 60
STUCK_DAYS = 14
OPEN_DECISIONS = ("open", "in_progress", "proposed")
VERIFIED = ("passed", "verified")
DONE_WORDS = ("done", "closed", "approved", "fixed", "resolved")


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

def _live(store) -> dict[str, dict]:
    return {u: r for u, r in store.requirement_map().items() if not r.get("deleted")}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _when(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _state_info(store, req: dict) -> dict[str, Any]:
    """Colour and whether the status is final, from the workflow of the item's own type."""
    wf = get_workflow_for_type(store.hierarchy, req.get("req_type", "functional"))
    state = next((s for s in (wf.states if wf else []) if s.id == req.get("status")), None)
    return {"colour": state.colour if state else DEFAULT_COLOUR, "terminal": bool(state and state.terminal),
            "label": state.label if state else str(req.get("status") or "")}


def _scope(store, live: dict[str, dict], product: Optional[str]) -> set[str]:
    """The uids in a product (its root requirements and everything below them), or all of them."""
    prod = store.product_map().get(product) if product else None
    roots = [r["uid"] for r in (prod or {}).get("root_requirements", []) if r.get("uid") in live]
    if not roots:
        return set(live)
    keep: set[str] = set()
    for root in roots:
        keep.add(root)
        keep.update(store.graph.descendants(root))
    return keep & set(live)


def _node(store, req: dict) -> dict[str, Any]:
    info = _state_info(store, req)
    return {"uid": req["uid"], "id": req.get("id"), "title": req.get("title", ""), "type": req.get("req_type"),
            "status": req.get("status"), "status_label": info["label"], "colour": info["colour"],
            "terminal": info["terminal"], "parent": req.get("parentId"),
            "verification": (req.get("verification") or {}).get("status") or "not_started"}


# ---------------------------------------------------------------------------
# Hierarchy (UI-22)
# ---------------------------------------------------------------------------

def hierarchy_tree(store, product: Optional[str] = None, types: Optional[list[str]] = None,
                   statuses: Optional[list[str]] = None, branch: Optional[str] = None,
                   limit: int = NODE_CAP) -> dict[str, Any]:
    """Items as a flat list with parents, in tree order. Filters keep the ancestors of every match so the shape
    stays readable. ``branch`` limits the view to one item and everything below it."""
    live = _live(store)
    keep = _scope(store, live, product)
    if branch and branch in live:
        keep = ({branch} | set(store.graph.descendants(branch))) & keep
    matches = {u for u in keep if (not types or live[u].get("req_type") in types)
               and (not statuses or live[u].get("status") in statuses)}
    shown_set = set(matches)
    for uid in list(matches):                    # keep the path to every match
        cur = live[uid].get("parentId")
        while cur and cur in keep and cur not in shown_set:
            shown_set.add(cur)
            cur = live[cur].get("parentId")
    children: dict[Optional[str], list[str]] = {}
    for uid in shown_set:
        parent = live[uid].get("parentId")
        children.setdefault(parent if parent in shown_set else None, []).append(uid)
    for kids in children.values():
        kids.sort(key=lambda u: (live[u].get("id") or u))
    ordered: list[dict[str, Any]] = []

    def walk(uid: str, depth: int) -> None:
        if len(ordered) >= limit or depth > 50:
            return
        node = _node(store, live[uid])
        node["depth"] = depth
        node["children"] = len(children.get(uid, []))
        node["match"] = uid in matches
        if node["parent"] not in shown_set:
            node["parent"] = None
        ordered.append(node)
        for child in children.get(uid, []):
            walk(child, depth + 1)

    for root in children.get(None, []):
        walk(root, 0)
    return {"nodes": ordered, "shown": len(ordered), "total": len(shown_set), "matched": len(matches),
            "capped": len(shown_set) > len(ordered)}


def type_structure_mermaid(store) -> dict[str, Any]:
    """Which item type may sit under which, as Mermaid text (ids are prefixed ``s_`` and labels are cleaned)."""
    h = store.hierarchy
    types = list(h.types)
    lines = ["flowchart TD"]
    if not types:
        return {"mermaid": "\n".join(lines + ['    empty["No item types"]']), "types": []}
    for t in types:
        cfg = h.types[t]
        lines.append(f'    s_{t}["{_text(cfg.label or t)}"]')
    for parent, rule in h.hierarchy.items():
        if parent not in h.types:
            continue
        for child in rule.allowed_children:
            if child in h.types:
                lines.append(f"    s_{parent} --> s_{child}")
    for t in types:
        colour = h.types[t].color if getattr(h.types[t], "color", "") else DEFAULT_COLOUR
        colour = colour if isinstance(colour, str) and colour.startswith("#") and len(colour) in (4, 7) else DEFAULT_COLOUR
        lines.append(f"    style s_{t} fill:{colour}33,stroke:{colour},color:#e6edf3")
    return {"mermaid": "\n".join(lines), "types": types, "enforce": h.enforce}


# ---------------------------------------------------------------------------
# Coverage (VIS-02)
# ---------------------------------------------------------------------------

def coverage_tree(store, by: str = "status", product: Optional[str] = None) -> dict[str, Any]:
    """The hierarchy with, for every item, how many items sit at or below it and a count per status
    (or per verification state). The UI draws it as a treemap and as a table."""
    if by not in ("status", "verification"):
        by = "status"
    data = hierarchy_tree(store, product=product, limit=10 ** 6)
    nodes = {n["uid"]: {**n, "kids": [], "by": {}, "count": 1} for n in data["nodes"]}
    for n in data["nodes"]:
        if n["parent"] in nodes:
            nodes[n["parent"]]["kids"].append(nodes[n["uid"]])
    colours: dict[str, str] = {}

    def fold(n: dict[str, Any]) -> None:
        key = n["status"] if by == "status" else n["verification"]
        colours.setdefault(str(key), n["colour"] if by == "status" else _VERIFY_COLOURS.get(str(key), DEFAULT_COLOUR))
        n["by"] = {str(key): 1}
        for kid in n["kids"]:
            fold(kid)
            n["count"] += kid["count"]
            for k, v in kid["by"].items():
                n["by"][k] = n["by"].get(k, 0) + v

    roots = [n for n in nodes.values() if not n["parent"]]
    for r in roots:
        fold(r)

    def clean(n: dict[str, Any], depth: int) -> dict[str, Any]:
        out = {k: n[k] for k in ("uid", "id", "title", "type", "status", "count", "by")}
        out["children"] = [clean(k, depth + 1) for k in n["kids"]] if depth < 6 else []
        return out

    totals: dict[str, int] = {}
    for r in roots:
        for k, v in r["by"].items():
            totals[k] = totals.get(k, 0) + v
    return {"by": by, "roots": [clean(r, 0) for r in roots], "totals": totals, "colours": colours,
            "total": sum(r["count"] for r in roots)}


_VERIFY_COLOURS = {"not_started": "#8b949e", "in_progress": "#d29922", "passed": "#2ea043", "verified": "#2ea043",
                   "failed": "#da3633", "waived": "#768390"}


# ---------------------------------------------------------------------------
# Impact graph (VIS-03)
# ---------------------------------------------------------------------------

def impact_graph(store, uid: str, depth: int = 2, types: Optional[list[str]] = None,
                 limit: int = GRAPH_CAP) -> Optional[dict[str, Any]]:
    """Everything within ``depth`` hops of an item: parents, children, linked items both ways, the decisions
    that affect it and the modules it is allocated to. Capped at ``limit`` nodes, nearest first."""
    live = _live(store)
    if uid not in live:
        return None
    depth = max(1, min(int(depth or 1), 3))
    decisions = [d for d in store.live_decisions()]
    by_ref: dict[str, list[dict]] = {}
    for d in decisions:
        for ref in d.get("affected_requirements") or []:
            by_ref.setdefault(str(ref), []).append(d)

    def neighbours(u: str) -> list[tuple[str, str, str]]:
        """(neighbour key, edge label, direction) for requirements, decisions (d:uid) and modules (m:id)."""
        r = live[u]
        out: list[tuple[str, str, str]] = []
        if r.get("parentId") in live:
            out.append((r["parentId"], "parent", "up"))
        out += [(c, "child", "down") for c in store.graph.children.get(u, []) if c in live]
        for rel in r.get("relationships") or []:
            t = relationship_target(rel)
            if t in live:
                out.append((t, rel.get("type", "link"), "up"))
        out += [(src, t or "link", "down") for src, t in store.graph.incoming.get(u, []) if src in live]
        for d in by_ref.get(u, []) + by_ref.get(r.get("id") or "", []):
            out.append((f"d:{d['uid']}", "decision", "up"))
        out += [(f"m:{m}", "allocated", "up") for m in r.get("allocated_to") or []]
        return out

    dist = {uid: 0}
    edges: list[tuple[str, str, str]] = []
    queue = deque([uid])
    while queue:
        cur = queue.popleft()
        if cur.startswith(("d:", "m:")) or dist[cur] >= depth:
            continue
        for nb, label, direction in neighbours(cur):
            if nb.startswith("d:") or nb.startswith("m:") or nb in live:
                if nb not in dist:
                    dist[nb] = dist[cur] + 1
                    queue.append(nb)
                edges.append((cur, nb, label) if direction == "up" else (nb, cur, label))

    def kind(key: str) -> str:
        return "decision" if key.startswith("d:") else "module" if key.startswith("m:") else "item"

    def describe(key: str) -> dict[str, Any]:
        if key.startswith("d:"):
            d = store.decision_map().get(key[2:], {})
            return {"key": key, "kind": "decision", "id": d.get("id", key[2:]), "title": d.get("title", ""),
                    "type": d.get("type", "decision"), "status": d.get("status"), "colour": "#a371f7"}
        if key.startswith("m:"):
            return {"key": key, "kind": "module", "id": key[2:], "title": key[2:], "type": "module",
                    "status": None, "colour": "#768390"}
        r = live[key]
        return {"key": key, "kind": "item", "id": r.get("id"), "title": r.get("title", ""),
                "type": r.get("req_type"), "status": r.get("status"), "colour": _state_info(store, r)["colour"]}

    ordered = sorted(dist, key=lambda k: (dist[k], str(k)))
    if types:
        ordered = [k for k in ordered if k == uid or kind(k) != "item" or live[k].get("req_type") in types]
    total = len(ordered)
    kept = ordered[:limit]
    keep = set(kept)
    nodes = [{**describe(k), "distance": dist[k]} for k in kept]
    seen: set[tuple[str, str, str]] = set()
    out_edges = []
    for a, b, label in edges:
        if a in keep and b in keep and (a, b, label) not in seen:
            seen.add((a, b, label))
            out_edges.append({"from": a, "to": b, "label": label})
    return {"uid": uid, "depth": depth, "nodes": nodes, "edges": out_edges, "shown": len(nodes), "total": total,
            "capped": total > len(nodes), "mermaid": _impact_mermaid(nodes, out_edges, uid)}


def _impact_mermaid(nodes: list[dict], edges: list[dict], focus: str) -> str:
    ids = {n["key"]: f"n{i}" for i, n in enumerate(nodes)}
    lines = ["flowchart LR"]
    for n in nodes:
        label = _text(f"{n['id']} {n['title']}", 48)
        lines.append(f'    {ids[n["key"]]}["{label}"]')
    for e in edges:
        lines.append(f'    {ids[e["from"]]} -->|"{_text(e["label"], 20)}"| {ids[e["to"]]}')
    for n in nodes:
        stroke = "#f0883e" if n["key"] == focus else n["colour"]
        lines.append(f'    style {ids[n["key"]]} fill:{n["colour"]}33,stroke:{stroke},color:#e6edf3')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Flow through the workflow (VIS-04)
# ---------------------------------------------------------------------------

def entered_status_at(req: dict) -> Optional[datetime]:
    """When the item reached its current status: the last recorded move into it, else when it was created."""
    for entry in reversed(req.get("history") or []):
        if entry.get("status_to") == req.get("status"):
            return _when(entry.get("date"))
    return _when(req.get("created"))


def flow(store, stuck_days: Optional[int] = None, type_filter: Optional[str] = None,
         now: Optional[datetime] = None) -> dict[str, Any]:
    """For each workflow, how many items sit in each state, how long they have been there and how many are
    stuck. States come from the repository's own workflows, so a custom workflow is drawn as defined."""
    now = now or _now()
    flow_cfg = getattr(store.hierarchy, "flow", None)
    limit = stuck_days if stuck_days is not None else (flow_cfg.stuck_days if flow_cfg else STUCK_DAYS)
    per_state = dict(flow_cfg.states) if flow_cfg else {}
    out: list[dict[str, Any]] = []
    live = _live(store)
    for wf_id, wf in store.hierarchy.workflows.items():
        used_by = sorted(t for t, cfg in store.hierarchy.types.items() if cfg.workflow == wf_id)
        if type_filter and type_filter not in used_by:
            continue
        rows = []
        for state in wf.states:
            ages: list[float] = []
            stuck: list[dict[str, Any]] = []
            threshold = per_state.get(state.id, limit)
            for r in live.values():
                if r.get("req_type") in used_by and r.get("status") == state.id:
                    since = entered_status_at(r)
                    age = round((now - since).total_seconds() / 86400, 1) if since else 0.0
                    ages.append(age)
                    if not state.terminal and age >= threshold:
                        stuck.append({"uid": r["uid"], "id": r.get("id"), "title": r.get("title", ""), "days": age})
            rows.append({"state": state.id, "label": state.label, "colour": state.colour, "terminal": state.terminal,
                         "count": len(ages), "avg_days": round(sum(ages) / len(ages), 1) if ages else 0.0,
                         "max_days": max(ages) if ages else 0.0, "threshold": threshold,
                         "stuck": sorted(stuck, key=lambda s: -s["days"])[:20], "stuck_count": len(stuck)})
        out.append({"workflow": wf_id, "types": used_by, "initial": wf.initial, "states": rows,
                    "transitions": {k: list(v) for k, v in wf.transitions.items()},
                    "total": sum(r["count"] for r in rows)})
    return {"stuck_days": limit, "workflows": out}


# ---------------------------------------------------------------------------
# Burn-up (VIS-05)
# ---------------------------------------------------------------------------

def _points(req: dict) -> float:
    try:
        value = float(req.get("estimate") or 0)
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0 else 1.0


def _done_at(store, req: dict) -> Optional[datetime]:
    info = _state_info(store, req)
    if not info["terminal"] or req.get("status") in ("cancelled", "canceled", "rejected", "deprecated"):
        return None
    return entered_status_at(req) or _when(req.get("last_modified"))


def burnup(store, iteration_id: str) -> Optional[dict[str, Any]]:
    """Scope against done over time for one iteration. An item enters the scope when it was created or when the
    iteration started, whichever is later (the tool does not record when an iteration field was set), and counts
    as done when it entered a final state that is not a cancellation."""
    from reqtool.iterations import IterationStore
    iteration = next((i for i in IterationStore(store.root).load_iterations() if i.get("id") == iteration_id), None)
    if iteration is None:
        return None
    start, end = _when(iteration.get("start_date")), _when(iteration.get("end_date"))
    items = [r for r in _live(store).values() if r.get("iteration") == iteration_id]
    events: list[tuple[datetime, float, float]] = []   # (when, scope delta, done delta)
    for r in items:
        added = _when(r.get("created")) or start or _now()
        if start and added < start:
            added = start
        pts = _points(r)
        events.append((added, pts, 0.0))
        done = _done_at(store, r)
        if done:
            events.append((max(done, added), 0.0, pts))
    events.sort(key=lambda e: e[0])
    series: list[dict[str, Any]] = []
    scope = done_pts = 0.0
    for when, ds, dd in events:
        scope += ds
        done_pts += dd
        day = when.date().isoformat()
        if series and series[-1]["date"] == day:
            series[-1].update(scope=scope, done=done_pts)
        else:
            series.append({"date": day, "scope": scope, "done": done_pts})
    return {"iteration": {"id": iteration_id, "title": iteration.get("title", ""), "start": iteration.get("start_date"),
                          "end": iteration.get("end_date")},
            "series": series, "scope": scope, "done": done_pts, "items": len(items),
            "unit": store.repo_enums.estimate_unit if getattr(store, "repo_enums", None) else "points",
            "note": "Scope steps are dated by when an item was created (or the iteration started)."}


# ---------------------------------------------------------------------------
# Decision ageing (VIS-07)
# ---------------------------------------------------------------------------

def decision_ageing(store, now: Optional[datetime] = None) -> dict[str, Any]:
    """Open decisions and open questions (TBDs), oldest and most blocking first, with the items each blocks."""
    now = now or _now()
    live = _live(store)
    by_id = {r.get("id"): r for r in live.values()}
    rows = []
    for d in store.live_decisions():
        if d.get("status") not in OPEN_DECISIONS:
            continue
        blocked = []
        for ref in d.get("affected_requirements") or []:
            r = live.get(ref) or by_id.get(ref)
            blocked.append({"uid": r["uid"], "id": r.get("id"), "title": r.get("title", ""), "status": r.get("status")}
                           if r else {"uid": None, "id": str(ref), "title": "", "status": None})
        created = _when(d.get("created"))
        rows.append({"uid": d["uid"], "id": d.get("id"), "title": d.get("title", ""), "kind": d.get("type", "decision"),
                     "status": d.get("status"), "priority": d.get("priority"), "owner": d.get("owner"),
                     "due": d.get("due"), "age_days": round((now - created).total_seconds() / 86400, 1) if created else 0.0,
                     "blocks": blocked})
    rows.sort(key=lambda r: (-len(r["blocks"]), -r["age_days"]))
    return {"decisions": rows, "total": len(rows), "oldest_days": max((r["age_days"] for r in rows), default=0.0)}


# ---------------------------------------------------------------------------
# Principle heatmap (VIS-09)
# ---------------------------------------------------------------------------

def principle_heatmap(store) -> dict[str, Any]:
    """Principle area and category against how many requirements cite each principle (a relationship or link from
    a requirement to the principle). Shows principles nobody uses and requirements no principle governs."""
    from reqtool.principles import UNPLACED, effective_vocabulary, placement
    live = _live(store)
    principles = {p["uid"]: p for p in store.live_principles()}
    cites: dict[str, set[str]] = {u: set() for u in principles}
    governed: set[str] = set()
    for uid, r in live.items():
        targets = [relationship_target(rel) for rel in r.get("relationships") or []]
        targets += [link.get("target_uid") for link in r.get("links") or [] if isinstance(link, dict)]
        for t in targets:
            if t in cites:
                cites[t].add(uid)
                governed.add(uid)
    vocab = effective_vocabulary(store.repo_enums.principle_areas)
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for uid, p in principles.items():
        area, cat = placement(p)
        cell = cells.setdefault((area or UNPLACED, cat or "general"),
                                {"principles": 0, "cited": 0, "citations": 0, "ids": [], "uncited": []})
        cell["principles"] += 1
        cell["citations"] += len(cites[uid])
        cell["ids"].append(p.get("id"))
        if cites[uid]:
            cell["cited"] += 1
        else:
            cell["uncited"].append(p.get("id"))
    areas = []
    order = list(vocab) + sorted({a for a, _c in cells if a not in vocab})
    for area in order:
        spec = vocab.get(area, {})
        cats = list(spec.get("categories", {})) + sorted({c for a, c in cells if a == area and c not in spec.get("categories", {})})
        row_cells = [{"category": c, "label": (spec.get("categories", {}).get(c) or {}).get("label", c.replace("_", " ").capitalize()),
                      **cells.get((area, c), {"principles": 0, "cited": 0, "citations": 0, "ids": [], "uncited": []})}
                     for c in cats]
        if any(c["principles"] for c in row_cells):
            areas.append({"area": area, "label": spec.get("label", area.replace("_", " ").capitalize()), "cells": row_cells})
    ungoverned = [r for r in live.values() if r["uid"] not in governed]
    return {"areas": areas, "principles": len(principles), "uncited": sum(1 for u in cites if not cites[u]),
            "requirements": len(live), "ungoverned": len(ungoverned),
            "ungoverned_sample": [{"uid": r["uid"], "id": r.get("id"), "title": r.get("title", "")} for r in ungoverned[:30]],
            "max": max((c["citations"] for a in areas for c in a["cells"]), default=0)}


def principle_citations(store, principle_uid: str) -> list[dict[str, Any]]:
    """The requirements that cite one principle."""
    live = _live(store)
    out = []
    for uid, r in live.items():
        targets = [relationship_target(rel) for rel in r.get("relationships") or []]
        targets += [link.get("target_uid") for link in r.get("links") or [] if isinstance(link, dict)]
        if principle_uid in targets:
            out.append({"uid": uid, "id": r.get("id"), "title": r.get("title", ""), "status": r.get("status")})
    return out


# ---------------------------------------------------------------------------
# Traceability grid (VIS-01)
# ---------------------------------------------------------------------------

GRID_COLUMNS = ("tests", "modules", "decisions")
GRID_COLUMN_CAP = 40


def trace_grid(store, columns: str = "tests", product: Optional[str] = None, req_type: Optional[str] = None,
               status: Optional[str] = None, gaps: bool = False, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    """Requirements down the side, tests, modules or decisions across the top. A cell says whether the link exists
    (and the state of the thing linked). ``gaps`` keeps only the rows with no link at all."""
    if columns not in GRID_COLUMNS:
        columns = "tests"
    live = _live(store)
    keep = _scope(store, live, product)
    reqs = [live[u] for u in keep if (not req_type or live[u].get("req_type") == req_type)
            and (not status or live[u].get("status") == status)]
    reqs.sort(key=lambda r: r.get("id") or r["uid"])
    decisions = {d["uid"]: d for d in store.live_decisions()}
    ref_to_dec: dict[str, list[str]] = {}
    for d in decisions.values():
        for ref in d.get("affected_requirements") or []:
            ref_to_dec.setdefault(str(ref), []).append(d["uid"])

    def links_for(r: dict) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        if columns == "tests":
            for ac in r.get("acceptance_criteria") or []:
                for ln in ac.get("links") or []:
                    if isinstance(ln, dict) and (ln.get("type") or "").lower() in ("test_case", "test", "tests"):
                        ref = str(ln.get("ref") or ln.get("title") or "")
                        if ref:
                            out[ref] = {"label": ref, "state": (r.get("verification") or {}).get("status") or "linked"}
        elif columns == "modules":
            for m in r.get("allocated_to") or []:
                out[str(m)] = {"label": str(m), "state": "allocated"}
        else:
            for uid in ref_to_dec.get(r["uid"], []) + ref_to_dec.get(r.get("id") or "", []):
                d = decisions[uid]
                out[d.get("id") or uid] = {"label": d.get("id") or uid, "state": d.get("status") or "linked"}
        return out

    rows = [(r, links_for(r)) for r in reqs]
    if gaps:
        rows = [(r, ln) for r, ln in rows if not ln]
    counts: dict[str, int] = {}
    for _r, ln in rows:
        for key in ln:
            counts[key] = counts.get(key, 0) + 1
    cols = sorted(counts, key=lambda k: (-counts[k], k))
    shown_cols = cols[:GRID_COLUMN_CAP]
    page = rows[offset: offset + limit]
    return {"columns_kind": columns, "columns": [{"key": k, "count": counts[k]} for k in shown_cols],
            "columns_total": len(cols),
            "rows": [{"uid": r["uid"], "id": r.get("id"), "title": r.get("title", ""), "type": r.get("req_type"),
                      "status": r.get("status"), "linked": len(ln),
                      "cells": {k: ln[k] for k in shown_cols if k in ln}} for r, ln in page],
            "total": len(rows), "offset": offset, "limit": limit,
            "all_requirements": len(reqs), "without_links": sum(1 for _r, ln in [(r, links_for(r)) for r in reqs] if not ln)}


def trace_grid_csv(grid: dict[str, Any]) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    keys = [c["key"] for c in grid["columns"]]
    w.writerow(["id", "title", "type", "status", *keys])
    for row in grid["rows"]:
        w.writerow([row["id"], row["title"], row["type"], row["status"],
                    *[(row["cells"].get(k) or {}).get("state", "") for k in keys]])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Roadmap board (UI-23, VIS-08)
# ---------------------------------------------------------------------------

ROADMAP_TYPES = ("theme", "initiative", "stakeholder_need")


def roadmap_board(store, group_by: str = "release") -> dict[str, Any]:
    """Themes as swim-lanes and releases (or iterations) as columns, initiatives as cards with progress, plus the
    dependency links between themes and initiatives and the longest dependency chain."""
    from reqtool.features import insight
    if group_by not in ("release", "iteration"):
        group_by = "release"
    live = _live(store)
    tree = insight.roadmap(store)
    unplanned = "unplanned"

    def column(r: dict) -> str:
        key = r.get("target_release") or r.get("release") if group_by == "release" else r.get("iteration")
        return str(key) if key else unplanned

    cards: list[dict[str, Any]] = []
    lanes: list[dict[str, Any]] = []

    def card(node: dict[str, Any], lane: str) -> dict[str, Any]:
        r = live[node["uid"]]
        return {**{k: node[k] for k in ("uid", "id", "title", "status", "req_type", "progress_pct", "children_count", "health")},
                "lane": lane, "column": column(r), "target_release": r.get("target_release") or r.get("release"),
                "iteration": r.get("iteration")}

    for top in tree:
        lane = top["uid"]
        lanes.append({"uid": lane, "id": top["id"], "title": top["title"], "req_type": top["req_type"],
                      "progress_pct": top["progress_pct"], "health": top["health"]})
        stack = [top] if top["req_type"] != "theme" else []
        stack += top.get("children", []) if top["req_type"] == "theme" else []
        if top["req_type"] == "theme" and not top.get("children"):
            stack = []
        for node in (stack if stack else [top]):
            cards.append(card(node, lane))
    needs = []
    for r in live.values():
        if r.get("req_type") == "stakeholder_need":
            links = [relationship_target(rel) for rel in r.get("relationships") or []]
            links += [src for src, _t in store.graph.incoming.get(r["uid"], [])]
            needs.append({"uid": r["uid"], "id": r.get("id"), "title": r.get("title", ""),
                          "links": [live[t].get("id") for t in links if t in live and live[t].get("req_type") in ROADMAP_TYPES]})
    columns = sorted({c["column"] for c in cards} - {unplanned})
    columns.append(unplanned)
    ids = {c["uid"] for c in cards} | {l["uid"] for l in lanes}
    deps = []
    for uid in ids:
        for rel in live[uid].get("relationships") or []:
            if rel.get("type") == "depends_on" and relationship_target(rel) in ids:
                deps.append({"from": uid, "to": relationship_target(rel)})
    chain = _critical_chain(deps)
    by_uid = {c["uid"]: c for c in cards} | {l["uid"]: l for l in lanes}
    return {"group_by": group_by, "columns": columns, "lanes": lanes, "cards": cards, "needs": needs,
            "dependencies": [{**d, "from_id": by_uid[d["from"]]["id"], "to_id": by_uid[d["to"]]["id"],
                              "critical": d["from"] in chain and d["to"] in chain} for d in deps],
            "critical_chain": [by_uid[u]["id"] for u in chain]}


def _critical_chain(deps: list[dict[str, str]]) -> list[str]:
    """Longest chain of ``from depends on to`` links, listed from the item that waits to the one it ends on.
    Loops are ignored (a chain never visits an item twice)."""
    graph: dict[str, list[str]] = {}
    for d in deps:
        graph.setdefault(d["from"], []).append(d["to"])
    best: list[str] = []

    def walk(node: str, path: list[str]) -> None:
        nonlocal best
        if len(path) > len(best):
            best = list(path)
        if len(path) > 40:
            return
        for nxt in graph.get(node, []):
            if nxt not in path:
                walk(nxt, path + [nxt])

    for start in list(graph):
        walk(start, [start])
    return best if len(best) > 1 else []


# ---------------------------------------------------------------------------
# Kanban card detail (VIS-06)
# ---------------------------------------------------------------------------

def kanban_details(store, board: dict[str, Any]) -> dict[str, Any]:
    """Add to every card its parent, what it waits on, how many children are still open and whether it breaks a
    parent/child rule; and list the iterations and people the board can be filtered by."""
    from reqtool import workflow_rules
    live = _live(store)
    broken: dict[str, str] = {}
    for hit in workflow_rules.audit(store.hierarchy, store.requirement_map()):
        if not hit["forced"] and hit["mode"] in ("warn", "error"):
            broken.setdefault(hit["uid"], hit["message"])
    for cards in board["columns"].values():
        for card in cards:
            r = live.get(card["uid"], {})
            parent = live.get(r.get("parentId") or "")
            waits = [live[t] for t in (relationship_target(rel) for rel in r.get("relationships") or []
                                       if rel.get("type") == "depends_on") if t in live]
            kids = [live[c] for c in store.graph.children.get(card["uid"], []) if c in live]
            card["parent"] = {"uid": parent["uid"], "id": parent.get("id"), "title": parent.get("title", "")} if parent else None
            card["blocked_by"] = [{"uid": w["uid"], "id": w.get("id")} for w in waits if not _state_info(store, w)["terminal"]]
            card["open_children"] = sum(1 for k in kids if not _state_info(store, k)["terminal"])
            card["rule_problem"] = broken.get(card["uid"])
    iterations: list[str] = []
    try:
        from reqtool.iterations import IterationStore
        iterations = [str(i.get("id")) for i in IterationStore(store.root).load_iterations() if i.get("id")]
    except Exception:
        iterations = []
    people = sorted({str(v) for r in live.values() for v in (r.get("assignee"), r.get("owner")) if v})
    return {**board, "iterations": iterations, "people": people}
