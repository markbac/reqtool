"""Grow the demo repository into a product family.

``populate_demo_data`` creates the sensor's systems requirements, decisions, principles and a thin agile layer.
``populate_family`` then adds what a real family has: more products (gateway, cloud platform, companion app),
themes down to tasks, five sprints of history, issues in every triage state, decisions with lineage, open
questions, principle citations, comments, reviews, saved views and automation rules.

Everything goes through the Store (and the requirement service for raising work from an issue and for a forced
move), so the data is what the tool itself would have produced. Dates are relative to the day the demo is made.
There is no git history in a new demo, so baselines and change sets are not created.
"""

from __future__ import annotations

import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import scaffold_demo_data as D
from ..fileio import save_yaml

NOW = datetime.now(timezone.utc).replace(microsecond=0)

# Sprint n: (start, end). Sprints 1 to 3 are complete, 4 is running, 5 is planned.
_SPRINT_START = {n: NOW - timedelta(days=7 + 14 * (4 - n)) for n in range(1, 6)}
SPRINTS = {n: (s, s + timedelta(days=13)) for n, s in _SPRINT_START.items()}


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _days(n: float) -> timedelta:
    return timedelta(days=n)


def _h(key: str) -> int:
    return zlib.crc32(key.encode())


class _Deferred:
    """Storage that keeps writes in memory until ``flush``: the demo touches each item many times while it builds
    its history, and writing every step to disk is slow. Reads see the pending data."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.pending: dict[Any, Any] = {}

    def write(self, path, data) -> None:
        self.pending[path] = data

    def read(self, path):
        return self.pending[path] if path in self.pending else self.inner.read(path)

    def exists(self, path) -> bool:
        return path in self.pending or self.inner.exists(path)

    def flush(self) -> None:
        for path, data in self.pending.items():
            self.inner.write(path, data)
        self.pending.clear()

    def __getattr__(self, name):
        return getattr(self.inner, name)


class Family:
    """Holds the store and the id to uid map while the family is built."""

    def __init__(self, root: Path, store) -> None:
        self.root, self.store = root, store
        self.ids: dict[str, str] = {}
        self.times: dict[str, dict[str, Optional[datetime]]] = {}
        self.counts: dict[str, int] = {}
        self.plans: list[tuple[str, dict[str, Any], str]] = []   # (uid, plan, author), applied after wiring
        self.codes: dict[str, str] = {}
        self.issue_ids: dict[str, str] = {}

    # -- lookups -----------------------------------------------------------------------------

    def refresh(self) -> None:
        for maps in (self.store.requirement_map(), self.store.decision_map(), self.store.principle_map()):
            for uid, item in maps.items():
                if item.get("id"):
                    self.ids[item["id"]] = uid

    def uid(self, item_id: str) -> str:
        if item_id not in self.ids:
            self.refresh()
        return self.ids[item_id]

    def req(self, item_id: str) -> dict[str, Any]:
        return self.store.requirement_map()[self.uid(item_id)]

    # -- history helpers -----------------------------------------------------------------------

    def _write(self, data: dict[str, Any]) -> None:
        self.store.storage.write(self.store.req_path(data["uid"]), data)

    def backdate_created(self, uid: str, when: datetime) -> None:
        data = self.store.requirement_map()[uid]
        data["created"] = data["last_modified"] = _iso(when)
        for entry in data.get("history") or []:
            entry["date"] = _iso(when)
        self._write(data)
        self.times.setdefault(uid, {})["created"] = when

    def move(self, uid: str, status: str, when: datetime, author: str = "reqtool", extra: Optional[dict] = None) -> None:
        """A dated status change. Refuses a move the item's workflow does not allow."""
        data = self.store.requirement_map()[uid]
        wf = self.store.get_workflow_for_type(data["req_type"])
        current = data["status"]
        if wf is not None and status not in wf.transitions.get(current, []):
            raise AssertionError(f"{data['id']}: {current} -> {status} is not a legal move")
        when = min(when, NOW - timedelta(minutes=5))
        self.store.update_requirement(uid, {"status": status, **(extra or {})}, author=author,
                                      summary=f"Status {current} to {status}.")
        data = self.store.requirement_map()[uid]
        data["history"][-1]["date"] = _iso(when)
        data["last_modified"] = _iso(when)
        self._write(data)
        t = self.times.setdefault(uid, {})
        if status in ("in_progress", "active") and not t.get("started"):
            t["started"] = when
        if status in ("done", "closed"):
            t["done"] = when

    def settle(self, uid: str) -> None:
        """Edits made while building happened at creation: give them the creation date."""
        data = self.store.requirement_map()[uid]
        created = self.times.get(uid, {}).get("created")
        if not created:
            return
        for entry in data.get("history") or []:
            if not entry.get("status_to"):
                entry["date"] = _iso(created)
        self._write(data)

    # -- creation ----------------------------------------------------------------------------

    def create(self, fields: dict[str, Any], created: datetime, author: str = "reqtool") -> dict[str, Any]:
        item = self.store.create_requirement(fields, author=author)
        self.ids[item["id"]] = item["uid"]
        self.backdate_created(item["uid"], created)
        return item

    def reset(self, uid: str) -> None:
        """Take an item the base demo created back to its first state so the dated path is the only history."""
        data = self.store.requirement_map()[uid]
        wf = self.store.get_workflow_for_type(data["req_type"])
        data["status"] = wf.initial if wf else "draft"
        data["history"] = data["history"][:1]
        self._write(data)

    def bump(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n


# ---------------------------------------------------------------------------
# Delivery paths
# ---------------------------------------------------------------------------

def _sprint_of(code: str) -> Optional[int]:
    return int(code[1]) if len(code) > 1 and code[1].isdigit() else None


def delivery_plan(key: str, code: str) -> dict[str, Any]:
    """Created date and the dated steps that lead to the status in ``code`` through legal moves only."""
    h, kind, n = _h(key), code[0], _sprint_of(code)
    steps: list[tuple[str, datetime]] = []
    if kind == "B":
        return {"created": NOW - _days(12 + h % 35), "steps": [], "iteration": None}
    assert n is not None
    start, end = SPRINTS[n]
    if code.endswith("s"):
        started = SPRINTS[3][0] + _days(3 + h % 3)
        return {"created": started - _days(8), "iteration": "sprint-04",
                "steps": [("ready", started - _days(2)), ("in_progress", started)]}
    if kind == "Y":
        ready = NOW - _days(1 + h % 3)
        return {"created": NOW - _days(10 + h % 10), "steps": [("ready", ready)], "iteration": f"sprint-0{n}"}
    created = start - _days(4 + h % 6)
    if kind == "X":
        return {"created": created, "steps": [("cancelled", start + _days(2))], "iteration": f"sprint-0{n}"}
    if h % 4:
        steps.append(("ready", start - _days(3)))
    t = start + _days(1 + h % 3)
    steps.append(("in_progress", t))
    if kind == "P":
        return {"created": created, "steps": steps, "iteration": f"sprint-0{n}"}
    if kind == "R" or h % 3:
        t = t + _days(2 + h % 3) if kind == "D" else NOW - _days(1 + h % 4)
        steps.append(("in_review", t))
    if kind == "D":
        t = min(t + _days(1 + h % 3), end - _days(1))
        steps.append(("done", t))
    return {"created": created, "steps": steps, "iteration": f"sprint-0{n}"}


def apply_plan(fam: Family, uid: str, plan: dict[str, Any], author: str) -> None:
    last = plan["created"]
    for status, when in plan["steps"]:
        when = max(when, last + timedelta(hours=1))
        fam.move(uid, status, when, author=author)
        last = when


def requirement_plan(key: str, code: str) -> dict[str, Any]:
    """Dated steps through the formal workflow, ending at a time that suits the state: approvals are old, reviews
    are recent, and a few reviews have sat for weeks."""
    h = _h(key)
    path = {"D": [], "I": ["in_review"], "R": ["in_review", "reviewed"], "A": ["in_review", "reviewed", "approved"]}[code]
    if code == "A":
        last = NOW - _days(12 + h % 90)
    elif code == "D":
        return {"created": NOW - _days(5 + h % 80), "steps": []}
    else:
        last = NOW - _days(1 + h % 9) if (h >> 7) % 10 < 7 else NOW - _days(20 + h % 40)
    gap = 2 + (h >> 3) % 6
    steps = [(state, last - _days(gap * (len(path) - 1 - i))) for i, state in enumerate(path)]
    return {"created": steps[0][1] - _days(gap), "steps": steps}


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def prepare(fam: Family) -> None:
    """Enums, iterations, rules and flow limits."""
    from ..fileio import load_yaml
    from ..iterations import IterationStore
    root, store = fam.root, fam.store
    enums_path = root / ".reqtool" / "enums.yaml"
    enums = load_yaml(enums_path)
    people = D.OWNERS + ["support.lead"]
    enums["owner"] = list(dict.fromkeys([*enums.get("owner", []), *people]))
    enums["team"] = list(dict.fromkeys([*enums.get("team", []), "cloud", "app", "gateway", "devops", "support"]))
    enums["tags"] = list(dict.fromkeys([*enums.get("tags", []), "alerts", "gateway", "privacy", "release-blocker"]))
    enums["team"] = list(dict.fromkeys([*enums["team"], "comms-security", "MOD-SENSOR-CORE", "MOD-POWER-MGMT"]))
    enums["id_domain"] = {**enums.get("id_domain", {}), "IN": "initiative", "SP": "spike", "ISS": "issue"}
    save_yaml(enums_path, enums)
    store.reload_enums()

    def day(d: datetime) -> str:
        return d.strftime("%Y-%m-%d")

    status = {1: "completed", 2: "completed", 3: "completed", 4: "active", 5: "planned"}
    capacity = {1: 34.0, 2: 38.0, 3: 44.0, 4: 60.0, 5: 45.0}
    goals = {1: "Boot, sensors and the first OTA skeleton", 2: "Secure boot path, cloud ingestion and telemetry schema",
             3: "Calibration, certificates and gateway boot", 4: "Gateway bridge, onboarding and rollouts",
             5: "Alerts, history graphs and certification evidence"}
    rows = [{"id": f"sprint-0{n}", "title": f"Sprint 0{n} - {goals[n]}", "methodology": "scrum",
             "start_date": day(SPRINTS[n][0]), "end_date": day(SPRINTS[n][1]), "capacity_story_points": capacity[n],
             "status": status[n], "notes": f"Goal: {goals[n]}."} for n in range(1, 6)]
    rows += [
        {"id": "gate-pdr", "title": "Phase Gate: Preliminary Design Review", "methodology": "waterfall",
         "milestone_date": day(NOW - _days(45)), "status": "completed", "gate_review_passed": True,
         "notes": "Requirements baseline accepted by the review board."},
        {"id": "gate-cdr", "title": "Phase Gate: Critical Design Review", "methodology": "waterfall",
         "milestone_date": day(NOW + _days(40)), "status": "planned", "gate_review_passed": False,
         "notes": "Needs the security and gateway requirements approved."},
        {"id": "gate-trr", "title": "Phase Gate: Test Readiness Review", "methodology": "waterfall",
         "milestone_date": day(NOW + _days(85)), "status": "planned", "gate_review_passed": False,
         "notes": "Verification evidence for release R1.0."},
        {"id": "release-r10", "title": "Release R1.0 - sensor, cloud ingestion, security", "methodology": "wagile",
         "start_date": day(NOW + _days(21)), "end_date": day(NOW + _days(60)), "milestone_date": day(NOW + _days(60)),
         "capacity_story_points": 90.0, "status": "planned", "notes": "Hybrid cycle: sprints with a release gate."},
    ]
    IterationStore(root).save_iterations(rows)

    # Parent and child rules: checks warn, one is an error so a forced move shows up, roll-ups are suggested.
    from ..workflow_rules import default_rules
    data = store.hierarchy_data()
    rules = default_rules("warn", "suggest")
    for rule in rules["rules"]:
        if rule["id"] == "finish-children-first":
            rule["mode"] = "error"
    data["rules"] = rules
    data["flow"] = {"stuck_days": 14, "states": {"in_review": 10, "reviewed": 30, "draft": 60, "backlog": 45, "in_triage": 10, "fixing": 21}}
    store.write_hierarchy(data)


def principles(fam: Family) -> None:
    from ..principles import default_vocabulary
    from ..services.principles import PrincipleService
    store = fam.store
    svc = PrincipleService(store)
    for area in D.PACKS:
        svc.add_pack(area)
    store.save_principle_vocabulary(default_vocabulary(D.PACKS + D.VOCABULARY_AREAS))
    fam.refresh()
    for pid, (area, category) in D.PRINCIPLE_PLACEMENT.items():
        store.update_principle(fam.uid(pid), {"area": area, "category": category}, summary="Placed in the vocabulary.")
    # Approve the principles the family relies on, with dates.
    for p in list(store.principle_map().values()):
        if p["id"] in D.CITATIONS or p["id"] in D.PRINCIPLE_PLACEMENT:
            p["status"] = "approved"
            p["approval"] = {"status": "approved", "approved_by": "systems.lead", "approved_date": _iso(NOW - _days(80))}
            p["review"] = {"last_reviewed": _iso(NOW - _days(80)), "reviewers": ["systems.lead", "security.lead"], "note": ""}
            store.storage.write(store.principle_path(p["uid"]), p)
    fam.bump("principles", len(store.principle_map()))


def products_and_needs(fam: Family) -> None:
    # Needs and requirements of the new products
    for need_id, title, text, owner in D.NEEDS:
        fam.create({"id": need_id, "title": title, "req_type": "stakeholder_need", "owner": owner,
                    "content": {"description": text, "rationale": "Captured from interviews and support tickets."}},
                   NOW - _days(95))
    for (rid, parent, rtype, title, text, why, prio, code, method, acs) in D.FAMILY_REQS:
        owner = {"GW": "gateway.lead", "CL": "cloud.lead", "APP": "app.lead"}[rid.split("-")[0]]
        fields: dict[str, Any] = {
            "id": rid, "title": title, "req_type": rtype, "parentId": fam.uid(parent), "owner": owner,
            "priority": prio, "verification_method": method,
            "content": {"description": text, "rationale": why},
            "domain": {"GW": "comms", "CL": "data", "APP": "ux"}[rid.split("-")[0]],
            "acceptance_criteria": [{"id": f"AC-{i}", "text": t, "uid": f"ac-{rid.lower()}-{i}",
                                     "links": ([{"system": "test_management", "type": "test_case", "ref": f"TC-{rid}-{i}",
                                                 "title": f"Test case for {rid} AC-{i}"}] if code in "AR" else [])}
                                    for i, t in enumerate(acs, 1)],
        }
        if rtype == "security":
            fields["allocated_to"] = ["comms-security"]
            fields["tags"] = ["security"]
        fam.create(fields, requirement_plan(rid, code)["created"])
        fam.bump("systems")


def move_requirements(fam: Family) -> None:
    """Status history for every systems requirement: new ones from the table, the original 203 by hash."""
    store = fam.store
    codes = {r[0]: r[7] for r in D.FAMILY_REQS}
    approvers = ["systems.lead", "security.lead", "qa.lead", "product.management"]
    for uid, r in list(store.requirement_map().items()):
        if r.get("req_type") in ("theme", "initiative", "epic", "feature", "story", "task", "bug", "spike", "issue"):
            continue
        rid = r["id"]
        if r.get("status") != "draft" or r.get("history", [{}])[-1].get("status_to"):
            continue
        h = _h(rid)
        code = codes.get(rid) or ("A" if h % 10 < 3 else "R" if h % 10 < 5 else "I" if h % 10 < 8 else "D")
        if rid in ("N-001",) or rid.startswith("SN-"):
            code = "A"
        evidence: dict[str, Any] = {}
        if rid in D.BASE_APPROVED:
            why, method, acs = D.BASE_APPROVED[rid]
            evidence = {"verification_method": method, "content": {"rationale": why},
                        "acceptance_criteria": [{"id": f"AC-{i}", "text": t, "uid": f"ac-{rid.lower()}-{i}",
                                                 "links": [{"system": "test_management", "type": "test_case", "ref": f"TC-{rid}-{i}",
                                                            "title": f"Test case for {rid} AC-{i}"}] if method == "test" else []}
                                                for i, t in enumerate(acs, 1)]}
            code = "A"
        elif code == "A" and rid not in codes and not rid.startswith("SN-") and rid != "N-001":
            code = "R" if h % 3 == 0 else "I" if h % 3 == 1 else "D"
        plan = requirement_plan(rid, code)
        if r["req_type"] == "stakeholder_need":
            plan["steps"] = [("active", plan["created"] + _days(5))]
        elif r["req_type"] == "safety":
            plan["steps"] = [s for s in plan["steps"] if s[0] != "approved"]  # safety approval needs a classification
        fam.backdate_created(uid, plan["created"])
        for state, when in plan["steps"]:
            extra = evidence if state == "in_review" else None
            if state == "approved":
                who = approvers[h % len(approvers)]
                extra = {"approval": {"status": "approved", "approved_by": who, "approved_date": _iso(when)},
                         "review": {"last_reviewed": _iso(when - _days(2)), "reviewers": [who], "note": ""}}
            fam.move(uid, state, when, author=approvers[(h >> 2) % len(approvers)], extra=extra)
        fam.bump("status_moves", len(plan["steps"]))


def verification(fam: Family) -> None:
    for rid, (status, note) in D.VERIFICATION.items():
        r = fam.req(rid)
        r["verification"] = {"status": status, "verified_date": _iso(NOW - _days(5 + _h(rid) % 30)) if status != "not_started" else None,
                             "note": note}
        fam._write(r)
    # Approved items that were never verified keep the default "not started".


def strategic(fam: Family) -> None:
    store = fam.store
    release = {i[0]: i[4] for i in D.INITIATIVES}
    for tid, title, desc, why, rel in D.THEMES:
        if title is None:
            th = fam.req(tid)
            store.update_requirement(th["uid"], {"target_release": rel, "custom_fields": {
                "outcome": "A certified sensor family people install in minutes and trust for years.",
                "success_measures": ["Setup in under 90 seconds", "24-month battery life", "4.5 star average rating"],
                "time_horizon": "now", "target_release": rel, "business_value": "critical"}}, summary="Describe the theme.")
            fam.reset(th["uid"])
            continue
        fam.create({"id": tid, "title": title, "req_type": "theme", "target_release": rel,
                    "content": {"description": desc, "rationale": why},
                    "custom_fields": {"outcome": desc, "time_horizon": "now" if rel == "R1.0" else "next",
                                      "target_release": rel, "business_value": "high",
                                      "success_measures": ["Delivered on the release date", "No release blockers open"]}},
                   NOW - _days(100))
    extras = {"IN-001": ("critical", ["Ships to retail on the R1.0 date", "Passes radio, EMC and PSTI review"], ["Certification slips"]),
              "IN-002": ("critical", ["10 000 devices ingested at p99 under 2 s"], ["Scale-out surprises"]),
              "IN-003": ("high", ["Onboarding under 90 s", "Crash-free sessions above 99.5 %"], ["Matter SDK differences"]),
              "IN-004": ("high", ["50 devices bridged at 250 ms"], ["SoC supply", "Thread interoperability"]),
              "IN-005": ("medium", ["Lite BOM at target", "Industrial pilot with two customers"], ["Cellular certification"]),
              "IN-006": ("high", ["No fleet-wide bad release"], ["Rollback complexity"]),
              "IN-007": ("critical", ["PSTI declaration signed", "Zero open high findings"], ["Pen test findings late"]),
              "IN-008": ("medium", ["Fewer than one false alert per sensor per month"], ["Model accuracy"])}
    for iid, theme, title, desc, rel in D.INITIATIVES:
        value, measures, risks = extras[iid]
        fam.create({"id": iid, "title": title, "req_type": "initiative", "parentId": fam.uid(theme), "target_release": rel,
                    "content": {"description": desc, "rationale": f"Part of release {rel}."},
                    "custom_fields": {"outcome": desc, "success_measures": measures, "risks": risks, "target_release": rel,
                                      "time_horizon": {"R1.0": "now", "R1.1": "next", "R2.0": "later"}[rel],
                                      "business_value": value}},
                   NOW - _days(90))
        fam.bump("initiatives")
    init_of = {e[0]: e[1] for e in D.EPICS}
    for eid, init, title, desc in D.EPICS:
        rel = release[init]
        if title is None:
            ep = fam.req(eid)
            store.update_requirement(ep["uid"], {"parentId": fam.uid(init), "target_release": rel,
                                                 "owner": "systems.lead"}, summary="Move under its initiative.")
            fam.reset(ep["uid"])
            continue
        fam.create({"id": eid, "title": title, "req_type": "epic", "parentId": fam.uid(init), "target_release": rel,
                    "owner": "systems.lead", "content": {"description": desc, "rationale": f"Delivers part of {init}."}},
                   NOW - _days(80))
    for fid, epic, title, desc in D.FEATURES:
        fam.create({"id": fid, "title": title, "req_type": "feature", "parentId": fam.uid(epic),
                    "target_release": release[init_of[epic]], "content": {"description": desc, "rationale": ""}},
                   NOW - _days(70))
    fam.bump("epics", len(D.EPICS))
    fam.bump("features", len(D.FEATURES))
    th = fam.req("TH-001")
    fam.reset(th["uid"])


MODULES = {"S": "MOD-SENSOR-CORE", "P": "MOD-POWER-MGMT", "C": "comms-security"}


def delivery(fam: Family) -> None:
    """Stories, tasks, spikes and defects. Items are created now; their dated paths are applied later."""
    store = fam.store

    def release(parent_id: str) -> Optional[str]:
        r = fam.req(parent_id)
        while r:
            if r.get("target_release"):
                return r["target_release"]
            r = store.requirement_map().get(r.get("parentId") or "")
        return None

    def plan_for(item_id: str, uid: str, code: str, author: str) -> dict[str, Any]:
        plan = delivery_plan(item_id, code)
        fam.codes[item_id] = code
        fam.plans.append((uid, plan, author))
        return plan

    # The items the base demo created are adopted: placed in the plan and given a dated path
    for item_id, (code, parent) in D.EXISTING_CODES.items():
        r = fam.req(item_id)
        plan = delivery_plan(item_id, code)
        fields: dict[str, Any] = {"iteration": plan["iteration"]}
        if item_id.startswith("TK"):
            fields = {"iteration": None, "estimate": None}  # tasks ride with their story's sprint and points
        if parent:
            fields["parentId"] = fam.uid(parent)
            fields["target_release"] = release(parent)
        store.update_requirement(r["uid"], fields, summary="Place in the plan.")
        fam.reset(r["uid"])
        fam.backdate_created(r["uid"], plan["created"])
        fam.codes[item_id] = code
        fam.plans.append((r["uid"], plan, r.get("assignee") or "reqtool"))
    for (sid, parent, title, pts, code, who, sat, mods, desc, acs) in D.STORIES:
        plan = delivery_plan(sid, code)
        fields = {"id": sid, "title": title, "req_type": "story", "parentId": fam.uid(parent), "estimate": pts,
                  "assignee": who, "iteration": plan["iteration"], "target_release": release(parent),
                  "content": {"description": desc, "rationale": ""},
                  "acceptance_criteria": [{"id": f"AC-{i}", "text": t, "uid": f"ac-{sid.lower()}-{i}",
                                           "links": ([{"system": "test_management", "type": "test_case", "ref": f"TC-{sid}-{i}",
                                                       "title": f"Test {sid} AC-{i}"}] if code[0] in "DR" else [])}
                                          for i, t in enumerate(acs, 1)]}
        if mods:
            fields["allocated_to"] = [MODULES[m] for m in mods]
        item = fam.create(fields, plan["created"], author=who)
        fam.codes[sid] = code
        fam.plans.append((item["uid"], plan, who))
        fam.bump("stories")

    # Tasks follow their story: the first of several is done while the story is still running
    by_story: dict[str, list[str]] = {"US-001": ["TK-001"], "US-002": ["TK-002"]}
    for tid, story, _title, _pts in D.TASKS:
        by_story.setdefault(story, []).append(tid)
    for tid, story, title, pts in D.TASKS:
        scode = fam.codes[story]
        first = by_story[story].index(tid) == 0 and len(by_story[story]) > 1
        if scode[0] == "P":
            code = ("D" + scode[1]) if first and not scode.endswith("s") else scode
        elif scode[0] == "R":
            code = "D" + scode[1]
        else:
            code = scode
        plan = delivery_plan(tid, code)
        who = fam.req(story).get("assignee") or "reqtool"
        item = fam.create({"id": tid, "title": title, "req_type": "task", "parentId": fam.uid(story),
                           "assignee": who, "target_release": fam.req(story).get("target_release"),
                           "allocated_to": fam.req(story).get("allocated_to") or [],
                           "content": {"description": title + ".", "rationale": ""}}, plan["created"], author=who)
        fam.codes[tid] = code
        fam.plans.append((item["uid"], plan, who))
        fam.bump("tasks")
    for sid, parent, title, pts, code, who, desc in D.SPIKES:
        plan = delivery_plan(sid, code)
        item = fam.create({"id": sid, "title": title, "req_type": "spike", "parentId": fam.uid(parent), "estimate": pts,
                           "assignee": who, "iteration": plan["iteration"], "target_release": release(parent),
                           "content": {"description": desc, "rationale": ""},
                           "acceptance_criteria": [{"id": "AC-1", "text": "Findings written up and shared.", "uid": f"ac-{sid.lower()}-1"}]},
                          plan["created"], author=who)
        fam.codes[sid] = code
        fam.plans.append((item["uid"], plan, who))
        fam.bump("spikes")
    for key, parent, title, prio, code, who, desc in D.BUGS:
        plan = delivery_plan("BG-" + key, code)
        item = fam.create({"title": title, "req_type": "bug", "parentId": fam.uid(parent), "priority": prio, "assignee": who,
                           "iteration": plan["iteration"], "target_release": release(parent),
                           "content": {"description": desc, "rationale": ""}}, plan["created"], author=who)
        fam.codes[item["id"]] = code
        fam.plans.append((item["uid"], plan, who))
        fam.bump("defects")


def run_plans(fam: Family) -> None:
    """Apply every dated delivery path, now that the items have all their links."""
    for uid, plan, author in fam.plans:
        apply_plan(fam, uid, plan, author)
        fam.bump("status_moves", len(plan["steps"]))


def issues(fam: Family) -> None:
    """Issues in every triage state; defects and accepted enhancements link to the work they led to."""
    from ..services.requirements import RequirementService
    store = fam.store
    svc = RequirementService(store, lambda event, payload: None)
    issue_ids: dict[str, str] = {}
    n = 0
    for spec in D.ISSUES:
        n += 1
        iid = f"ISS-{n:03d}"
        issue_ids[spec["key"]] = iid
        path = spec["path"]
        first_days = path[0][1] + (3 if path[0][0] != "reported" else 0)
        custom = {"reporter": spec["reporter"], "observed": spec["observed"], "expected": spec["expected"],
                  "steps": spec["steps"], "affected_version": spec["version"], "environment": spec["environment"]}
        if spec.get("note"):
            custom["triage_note"] = spec["note"]
        if spec.get("duplicate_of"):
            custom["duplicate_of"] = issue_ids[spec["duplicate_of"]]
        fields = {"id": iid, "title": spec["title"], "req_type": "issue", "priority": spec["priority"],
                  "content": {"description": spec["observed"], "rationale": ""}, "custom_fields": custom}
        if spec.get("assignee"):
            fields["assignee"] = spec["assignee"]
        item = fam.create(fields, NOW - _days(first_days), author=spec["reporter"])
        raised_at = None
        for state, days in path:
            if state == "reported":
                continue
            fam.move(item["uid"], state, NOW - _days(days), author=spec.get("assignee") or "support.lead")
            if state in ("defect", "enhancement") and spec.get("raise") and raised_at is None:
                raised_at = NOW - _days(days)
        fam.bump("issues")
        link = spec.get("link")
        if spec.get("raise") == "defect":
            bug = svc.raise_from(item["uid"], "bug")
            assert link is not None
            parent_uid = fam.uid(link)
            store.update_requirement(bug["uid"], {"parentId": parent_uid, "assignee": spec["assignee"],
                                                  "target_release": fam.req(link).get("target_release")}, summary="File under the story it affects.")
            fam.ids[bug["id"]] = bug["uid"]
            state = path[-1][0]
            plan_code = {"defect": "Y5", "fixing": "P4", "fixed": "D4", "closed": "D4"}[state]
            plan = delivery_plan(bug["id"], plan_code)
            plan["created"] = raised_at or plan["created"]
            plan["steps"] = [(st, max(w, plan["created"] + _days(1))) for st, w in plan["steps"]]
            store.update_requirement(bug["uid"], {"iteration": plan["iteration"]}, summary="Assign to the sprint.")
            fam.backdate_created(bug["uid"], plan["created"])
            fam.codes[bug["id"]] = plan_code
            fam.plans.append((bug["uid"], plan, spec["assignee"]))
            fam.bump("defects")
        elif link:
            target = fam.req(link)
            rels = list(target.get("relationships") or [])
            rels.append({"type": "derived_from", "target": {"uid": item["uid"], "id": iid}})
            store.update_requirement(target["uid"], {"relationships": rels}, summary=f"Derived from {iid}.")
    fam.issue_ids = issue_ids


def derive_parents(fam: Family) -> None:
    """Parent status follows its children, bottom-up, so the parent and child rules hold. Stories keep the status
    from the tables; features, epics, initiatives and themes are derived."""
    store = fam.store
    started_states = {"in_progress", "in_review", "done", "active"}
    for level in ("feature", "epic", "initiative", "theme"):
        wf = store.get_workflow_for_type(level)
        first = "active" if wf.initial == "draft" else "in_progress"
        for uid, r in list(store.requirement_map().items()):
            if r.get("req_type") != level:
                continue
            kids = [k for k in store.requirement_map().values() if k.get("parentId") == uid and not k.get("deleted")]
            if not kids:
                continue
            kid_times = [fam.times.get(k["uid"], {}) for k in kids]
            earliest = min((t.get("created") or NOW) for t in kid_times)
            fam.backdate_created(uid, earliest - _days(5 + _h(r["id"]) % 6))
            kid_status = [k["status"] for k in kids]
            begins = [b for b in ((t.get("started") or t.get("done")) for t, k in zip(kid_times, kids)
                                  if k["status"] in started_states) if b is not None]
            if all(s in ("done", "cancelled") for s in kid_status) and "done" in kid_status:
                done_at = max(t.get("done") or NOW for t, k in zip(kid_times, kids) if k["status"] == "done") + timedelta(hours=2)
                begin = min(begins) if begins else done_at - _days(1)
                fam.move(uid, first, begin - timedelta(hours=1), author="systems.lead")
                fam.move(uid, "done", done_at, author="systems.lead")
            elif any(s in started_states for s in kid_status):
                begin = min(begins) if begins else NOW - _days(3)
                fam.move(uid, first, begin - timedelta(hours=1), author="systems.lead")
    fam.bump("derived")


def wire(fam: Family) -> None:
    """Relationships: satisfies, implements, traces_to, derived_from, depends_on, conflicts_with and principle citations."""
    store = fam.store

    def rel(kind: str, target_id: str) -> dict[str, Any]:
        t = store.requirement_map().get(fam.uid(target_id)) or store.principle_map().get(fam.uid(target_id))
        return {"type": kind, "target": {"uid": t["uid"], "id": t.get("id")}}

    adds: dict[str, list[dict[str, Any]]] = {}

    def add(item_id: str, kind: str, target_id: str) -> None:
        adds.setdefault(item_id, []).append(rel(kind, target_id))

    for row in D.STORIES:
        if row[6]:
            add(row[0], "satisfies", row[6])
    for tid, kind, target in (("US-001", "satisfies", "SYS-SEN-1"), ("US-002", "satisfies", "SYS-SEC-5"), ("US-003", "satisfies", "SYS-ECO-3"),
                              ("US-004", "satisfies", "CL-FR-1"), ("US-005", "satisfies", "CL-FR-3")):
        add(tid, kind, target)
    for tid, target in (("TK-007", "SYS-SEC-4"), ("TK-018", "SYS-SEC-2"), ("TK-025", "GW-SC-1"), ("TK-032", "SYS-SEC-6"), ("TK-002", "SYS-SEC-6")):
        add(tid, "implements", target)
    for item, need in (("TH-001", "N-001"), ("IN-001", "N-001"), ("IN-002", "SN-CL-1"), ("IN-003", "SN-APP-1"), ("IN-004", "SN-GW-1"),
                       ("EP-008", "SN-GW-1"), ("EP-007", "SN-APP-1"), ("EP-006", "SN-CL-1")):
        add(item, "traces_to", need)
    for src, dst in (("IN-004", "IN-002"), ("IN-003", "IN-002"), ("IN-006", "IN-002"), ("EP-009", "EP-008"), ("EP-007", "EP-006"),
                     ("US-052", "US-049"), ("US-053", "US-050"), ("US-039", "US-006"), ("US-061", "US-031"), ("US-062", "US-061"),
                     ("US-072", "US-070"), ("US-035", "US-034"), ("US-033", "US-030"), ("US-032", "US-031"), ("US-012", "US-011"),
                     ("US-047", "US-046"), ("US-071", "US-070"), ("US-042", "US-072"), ("GW-FR-2", "GW-FR-1"), ("CL-FR-4", "CL-FR-1"),
                     ("CL-FR-5", "CL-FR-2")):
        add(src, "depends_on", dst)
    add("SYS-SEN-4", "conflicts_with", "SYS-PWR-2")
    for pid, items in D.CITATIONS.items():
        for item_id in items:
            if item_id in fam.ids or item_id in {r.get("id") for r in store.requirement_map().values()}:
                add(item_id, "relates_to", pid)
    for item_id, extra in adds.items():
        r = fam.req(item_id)
        have = {(x["type"], x["target"]["uid"]) for x in r.get("relationships") or []}
        new = [x for x in extra if (x["type"], x["target"]["uid"]) not in have]
        if new:
            store.update_requirement(r["uid"], {"relationships": [*(r.get("relationships") or []), *new]}, summary="Link related items.")
            fam.settle(r["uid"])
            fam.bump("links", len(new))


def decisions(fam: Family) -> None:
    store = fam.store
    fam.refresh()
    for d in D.DECISIONS:
        content = {"context": d["context"], "description": d["title"], "options": d["options"],
                   "chosen_option": d["chosen"], "rationale": d["rationale"], "impact": ""}
        affected = [fam.uid(i) for i in d["affects"] if i in fam.ids or i in {r.get("id") for r in store.requirement_map().values()}]
        fields = {"id": d["id"], "title": d["title"], "status": "proposed", "owner": d["owner"], "content": content,
                  "tags": d["tags"], "affected_requirements": affected}
        if d.get("supersedes"):
            fields["supersedes"] = fam.uid(d["supersedes"])
        item = store.create_decision(fields, author=d["owner"])
        fam.ids[d["id"]] = item["uid"]
        if d["status"] != "proposed":
            store.update_decision(item["uid"], {"status": d["status"]}, summary=f"Decision {d['status']}.", author=d["owner"])
        _date_item(store, item["uid"], NOW - _days(d["age"]), decision=True)
        fam.bump("decisions")
    # Open questions
    for t in D.TBDS:
        content = {"description": t["text"], "impact": t["impact"], "resolution_criteria": f"Decision needed by {t['needed']}.",
                   "resolution": t.get("resolution")}
        affected = [fam.uid(i) for i in t["affects"] if i in {r.get("id") for r in store.requirement_map().values()}]
        item = store.create_tbd({"id": t["id"], "title": t["title"], "content": content, "status": "open", "priority": t["priority"],
                                 "owner": t["owner"], "affected_requirements": affected, "tags": ["open-question"]}, author=t["owner"])
        fam.ids[t["id"]] = item["uid"]
        _date_item(store, item["uid"], NOW - _days(20 + _h(t["id"]) % 50), decision=True)
        if t["state"] != "open":
            _resolve_tbd(fam, t["id"], t)
        fam.bump("tbds")
    fam.refresh()
    for tid, upd in D.EXISTING_TBD_UPDATES.items():
        _resolve_tbd(fam, tid, upd)
    # Decisions that came from earlier questions
    for dec in ("DEC-001", "DEC-002", "DEC-003", "DEC-004", "DEC-005", "DEC-007"):
        uid = fam.uid(dec)
        item = store.decision_map()[uid]
        item["affected_requirements"] = item.get("affected_requirements") or []
        _date_item(store, uid, NOW - _days(100 + _h(dec) % 40), decision=True)


def _resolve_tbd(fam: Family, tbd_id: str, spec: dict[str, Any]) -> None:
    store = fam.store
    uid = fam.uid(tbd_id)
    fields: dict[str, Any] = {"status": spec["state"]}
    if spec.get("resolution"):
        fields["content"] = {"resolution": spec["resolution"]}
    if spec.get("resolves_into"):
        fields["resolution_ref"] = fam.uid(spec["resolves_into"])
    store.update_tbd(uid, fields, summary=f"Question {spec['state'].replace('_', ' ')}.")
    if spec["state"] == "resolved" and spec.get("resolves_into"):
        fam.bump("resolved_tbds")


def _date_item(store, uid: str, when: datetime, decision: bool = False) -> None:
    data = store.decision_map()[uid]
    data["created"] = _iso(when)
    entries = data.get("history") or []
    for i, entry in enumerate(entries):
        entry["date"] = _iso(when + timedelta(days=i * 2))
    data["last_modified"] = _iso(when + timedelta(days=max(len(entries) - 1, 0) * 2))
    store.storage.write(store.decision_path(uid), data)


def collaboration(fam: Family) -> None:
    from ..features import reviews
    from ..stores import comment_store
    store = fam.store
    fam.refresh()
    for item_id, thread in D.COMMENTS:
        uid = fam.uid(item_id)
        made: list[dict[str, Any]] = []
        for i, (author, text, reply) in enumerate(thread):
            c = store.add_comment(uid, text, author, reply_to=made[reply]["uid"] if reply is not None else None)
            made.append(c)
        comments = comment_store.get_comments(store.root, uid)
        for i, c in enumerate(comments):
            c["created_at"] = _iso(NOW - _days(max(0.2, 6 - i * 0.7 - _h(item_id) % 3)))
        if item_id in ("US-009", "SYS-SEC-2"):
            comments[0]["resolved"] = True
        save_yaml(comment_store.comments_path(store.root, uid), comments)
        fam.bump("comments", len(thread))
    for item_id, reviewers, by, approved in D.REVIEWS:
        uid = fam.uid(item_id)
        reviews.request_review(store, uid, reviewers, by)
        for who in approved:
            reviews.record_approval(store, uid, who)
        fam.bump("reviews", len(reviewers))
    for preset in D.PRESETS:
        store.save_filter_preset(preset)
    from ..automation import AutomationEngine
    AutomationEngine(fam.root).save_rules(D.AUTOMATION_RULES)
    for item_id, name, text, note in D.ATTACHMENTS:
        store.add_attachment(fam.uid(item_id), name, text.encode(), author="qa.lead", description=note)
        fam.bump("attachments")


def force_one(fam: Family) -> None:
    """Close a story with a task still open, which the 'finish children first' rule forbids unless forced with a reason."""
    from ..services.requirements import RequirementService
    svc = RequirementService(fam.store, lambda event, payload: None)
    uid = fam.uid("US-047")
    svc.update(uid, {"status": "done"}, force=True,
               reason="In-order replay (TK-037) moves to the diagnostics story. QA agreed that buffering ships without it for the beta.",
               actor={"name": "systems.lead"})
    data = fam.store.requirement_map()[uid]
    when = _iso(NOW - _days(1))
    for entry in data["history"][-2:]:
        entry["date"], entry["modified_by"] = when, "systems.lead"
    data["attributes"]["forced"].update(at=when, by="systems.lead")
    fam._write(data)
    fam.bump("forced")


def products(fam: Family) -> None:
    """Product manifests and the requirements each product is made of."""
    store = fam.store
    roots = {
        "env-sensor-v1": ["N-001", "TH-001"],
        "thread_gateway": ["SN-GW-1", "IN-004"],
        "cloud_platform": ["SN-CL-1", "TH-003"],
        "companion_app": ["SN-APP-1", "IN-003"],
    }
    from ..fileio import uuid7, utcnow_iso
    from .. import __version__
    now = utcnow_iso()
    for p in D.PRODUCTS:
        pdir = fam.root / "products" / p["id"]
        pdir.mkdir(parents=True, exist_ok=True)
        save_yaml(pdir / "_product.yaml", {
            "schema_version": "1.0.0", "type": "product", "tool_version": __version__, "uid": uuid7(), "id": p["id"],
            "title": p["title"], "version": "1.0.0", "content": {"description": p["description"]},
            "modules": p["modules"], "root_requirements": [], "display_order": [],
            "content_hash": "", "created": now, "last_modified": now, "history": []})
    store.reload_modules()
    issue_product = {"hum": "env-sensor-v1", "gh": "env-sensor-v1", "night": "env-sensor-v1", "batt": "env-sensor-v1",
                     "dup": "env-sensor-v1", "led": "env-sensor-v1", "cold": "env-sensor-v1", "co2": "env-sensor-v1",
                     "reboot": "thread_gateway", "ota": "env-sensor-v1", "twice": "cloud_platform",
                     "fahr": "companion_app", "safari": "companion_app", "setup": "companion_app"}
    for key, product in issue_product.items():
        roots[product].append(fam.issue_ids[key])
    for pid, ids in roots.items():
        prod = store.product_map().get(pid)
        if prod is None:
            continue
        path = fam.root / "products" / pid / "_product.yaml"
        from ..fileio import load_yaml
        data = load_yaml(path)
        data["root_requirements"] = [{"uid": fam.uid(i)} for i in ids]
        save_yaml(path, data)
    store.reload_modules()
    for p in D.PRODUCTS:
        for mod in p["modules"]:
            if mod["id"] in store.module_map():
                try:
                    store.import_module(p["id"], mod["id"])
                except Exception:
                    pass
    fam.bump("products", len(D.PRODUCTS))


def _parse(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def finalise(fam: Family) -> None:
    """Put each history in date order (entries written while building, such as forced moves and suspect flags, keep
    their place), then seal every artefact again: direct edits leave stale hashes."""
    from ..artefacts import DECISION, PRINCIPLE, REQUIREMENT, history_entry
    from ..graph import relationship_target
    store = fam.store
    # Building the items flags links as suspect each time an upstream item moves. Clear those, then leave three
    # real ones: a story whose requirement was edited after the link was made.
    for data in store.requirement_map().values():
        for rel in data.get("relationships") or []:
            rel.pop("suspect", None)
        data["history"] = [h for h in data.get("history") or [] if "became suspect" not in h.get("summary", "")]
    for story_id, upstream_id in (("US-002", "SYS-SEC-5"), ("US-065", "SYS-SEC-6"), ("US-014", "SYS-SEN-4")):
        story, up = fam.req(story_id), fam.req(upstream_id)
        for rel in story.get("relationships") or []:
            if relationship_target(rel) == up["uid"]:
                rel["suspect"] = True
        story["history"].append(history_entry(story["version"], "reqtool",
                                              f"Link to {upstream_id} became suspect (upstream change)", now=_iso(NOW - _days(3))))
    for uid, data in store.requirement_map().items():
        prev = None
        for entry in data.get("history") or []:
            when = _parse(entry["date"])
            if prev is not None and when < prev:
                when = prev
            if when > NOW:
                when = max(prev or NOW - _days(1), NOW - _days(1))
            entry["date"] = _iso(when)
            prev = when
        if data.get("history"):
            data["last_modified"] = data["history"][-1]["date"]
        data["content_hash"] = REQUIREMENT.hash_fn(data)
        store.storage.write(store.req_path(uid), data)
    for uid, data in store.principle_map().items():
        data["content_hash"] = PRINCIPLE.hash_fn(data)
        store.storage.write(store.principle_path(uid), data)
    for uid, data in store.decision_map().items():
        data["content_hash"] = DECISION.hash_fn(data)
        store.storage.write(store.decision_path(uid), data)


def populate_family(root: Path, store) -> dict[str, int]:
    fam = Family(root, store)
    fam.refresh()
    prepare(fam)
    real = store.storage
    store.storage = _Deferred(real)
    try:
        principles(fam)
        strategic(fam)
        products_and_needs(fam)
        delivery(fam)
        issues(fam)
        wire(fam)
        for uid in list(store.requirement_map()):
            fam.settle(uid)
        run_plans(fam)
        move_requirements(fam)
        derive_parents(fam)
        verification(fam)
        decisions(fam)
        collaboration(fam)
        store.storage.flush()
    finally:
        store.storage = real
    products(fam)
    force_one(fam)
    store.storage = _Deferred(real)
    try:
        finalise(fam)
        store.storage.flush()
    finally:
        store.storage = real
    return fam.counts
