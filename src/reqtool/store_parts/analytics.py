"""Impact analysis, estimate roll-ups, progress and kanban views over the artefact graph."""

from __future__ import annotations

import logging
from typing import Any, Optional

from reqtool.graph import relationship_target

log = logging.getLogger(__name__)


class AnalyticsMixin:
    def compute_impact(self, uid: str) -> dict[str, Any]:
        """
        Return the transitive downstream impact closure for a requirement.
        Downstream: items that depend on / are derived from / implement / satisfy `uid`.
        Upstream: items that `uid` depends on / is derived from.
        """
        downstream: list[dict] = []
        for dep_uid, rel_type in self.graph.downstream(uid, self.IMPACT_REL_TYPES):
            dep = self.requirements[dep_uid]
            downstream.append({
                "uid": dep_uid,
                "id": dep.get("id", ""),
                "title": dep.get("title", ""),
                "status": dep.get("status", ""),
                "req_type": dep.get("req_type", ""),
                "rel_type": rel_type,
            })

        # Direct upstream (not transitive for brevity)
        req = self.requirements.get(uid, {})
        upstream: list[dict] = []
        for rel in req.get("relationships", []):
            tgt = relationship_target(rel)
            if tgt and rel.get("type", "") in self.IMPACT_REL_TYPES:
                tgt_req = self.requirements.get(tgt, {})
                upstream.append({
                    "uid": tgt,
                    "id": tgt_req.get("id", ""),
                    "title": tgt_req.get("title", ""),
                    "status": tgt_req.get("status", ""),
                    "req_type": tgt_req.get("req_type", ""),
                    "rel_type": rel.get("type", ""),
                })

        # Group downstream by type
        by_type: dict[str, list[dict]] = {}
        for item in downstream:
            by_type.setdefault(item.get("req_type", "unknown"), []).append(item)

        return {
            "uid": uid,
            "downstream_count": len(downstream),
            "downstream_by_type": by_type,
            "upstream": upstream,
        }

    # ------------------------------------------------------------------
    # Estimate rollup
    # ------------------------------------------------------------------

    def _live_descendants(self, uid: str) -> list[dict[str, Any]]:
        """All non-deleted descendants of ``uid`` (cycle-safe), excluding ``uid`` itself."""
        return [self.requirements[u] for u in self.graph.descendants(uid)]

    def _rollup_leaves(self, uid: str) -> list[dict[str, Any]]:
        """Descendants of ``uid`` that have no live children of their own (cancelled items excluded)."""
        desc = self._live_descendants(uid)
        parents = {r.get("parentId") for r in desc}
        return [r for r in desc if r.get("uid") not in parents and r.get("status") != "cancelled"]

    def compute_estimate_rollup(self, uid: str) -> Optional[float]:
        """Sum of the estimates of all leaf descendants (a parent's own estimate is never double counted).

        None if there are no descendants or none of the leaves has an estimate.
        """
        estimates = [r["estimate"] for r in self._rollup_leaves(uid) if r.get("estimate") is not None]
        return sum(estimates) if estimates else None

    # ------------------------------------------------------------------
    # Kanban
    # ------------------------------------------------------------------

    def build_kanban(
        self,
        req_type: Optional[str] = None,
        iteration: Optional[str] = None,
        owner: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Return a column-per-state kanban board.
        Cards contain: uid, id, title, assignee, estimate, priority, req_type.
        """
        # Determine which workflow to show
        if req_type:
            wf = self.get_workflow_for_type(req_type)
        else:
            wf = None

        if wf:
            states = [s.id for s in wf.states]
        else:
            # Fall back to config workflow
            states = [s.id for s in self.config.workflow.states]

        columns: dict[str, list[dict]] = {s: [] for s in states}
        columns["_uncolumned"] = []

        for uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            if req_type and req.get("req_type") != req_type:
                continue
            if iteration and req.get("iteration") != iteration:
                continue
            if owner and req.get("owner") != owner:
                continue
            if assignee and req.get("assignee") != assignee:
                continue

            card = {
                "uid": uid,
                "id": req.get("id", ""),
                "title": req.get("title", ""),
                "assignee": req.get("assignee"),
                "owner": req.get("owner"),
                "estimate": req.get("estimate"),
                "priority": req.get("priority", "medium"),
                "req_type": req.get("req_type", "functional"),
                "iteration": req.get("iteration"),
            }
            status = req.get("status", "draft")
            if status in columns:
                columns[status].append(card)
            else:
                columns["_uncolumned"].append(card)

        if not columns["_uncolumned"]:
            del columns["_uncolumned"]

        return {
            "states": states,
            "columns": columns,
            "req_type": req_type,
        }

    # ------------------------------------------------------------------
    # Filter presets
    # ------------------------------------------------------------------

    def _done_states(self, req_type: str) -> set[str]:
        """Terminal workflow states other than ``cancelled`` for the type (falls back to the global workflow)."""
        wf = self.get_workflow_for_type(req_type)
        states = wf.states if wf and wf.states else self.config.workflow.states
        return {s.id for s in states if s.terminal and s.id != "cancelled"}

    def compute_progress_rollup(self, uid: str) -> dict[str, Any]:
        """Progress of ``uid`` over its leaf descendants.

        An item is done when it is in a terminal state of its own workflow (``cancelled`` is not
        completion and is left out of the totals). The root is excluded; ``active`` is not done.
        With no descendants the item's own state decides.
        """
        target = self.requirements.get(uid)
        if not target:
            return {"uid": uid, "total_items": 0, "done_items": 0, "total_estimate": 0.0, "done_estimate": 0.0, "progress_pct": 0.0}

        items = self._rollup_leaves(uid)
        if not items and target.get("status") != "cancelled":
            items = [target]

        total_estimate = done_estimate = 0.0
        done_items = 0
        done_cache: dict[str, set[str]] = {}
        for item in items:
            est = float(item.get("estimate") or 0.0)
            rt = item.get("req_type", "")
            if rt not in done_cache:
                done_cache[rt] = self._done_states(rt)
            total_estimate += est
            if item.get("status") in done_cache[rt]:
                done_items += 1
                done_estimate += est

        total_items = len(items)
        pct = round(done_estimate / total_estimate * 100.0, 1) if total_estimate > 0 else (
            round(done_items / total_items * 100.0, 1) if total_items else 0.0)
        return {
            "uid": uid,
            "id": target.get("id", ""),
            "title": target.get("title", ""),
            "total_items": total_items,
            "done_items": done_items,
            "total_estimate": total_estimate,
            "done_estimate": done_estimate,
            "progress_pct": pct,
        }
