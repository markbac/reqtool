"""
reqtool.graph
=============
The traceability graph over requirements: parent/child hierarchy and relationship links.

One place defines what a relationship reference looks like and how the graph is walked, so
impact analysis, roll-ups and suspect-link marking cannot disagree. A graph is an immutable
snapshot built in one pass; the store caches it until the next write.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Iterable, Mapping, Optional


def relationship_target(rel: Any) -> Optional[str]:
    """The uid a relationship points at. Accepts ``{"target": {"uid": ...}}``, ``{"target": "<uid>"}``
    and the older flat ``{"uid": ...}`` shape, and returns None for anything else."""
    if not isinstance(rel, Mapping):
        return None
    target = rel.get("target")
    if isinstance(target, Mapping):
        return target.get("uid") or rel.get("uid") or None
    if isinstance(target, str) and target:
        return target
    return rel.get("uid") or None


class TraceabilityGraph:
    """Children and incoming links of the live (non-deleted) requirements."""

    def __init__(self, requirements: Mapping[str, Mapping[str, Any]]):
        self.children: dict[str, list[str]] = {}
        # target uid -> [(source uid, relationship type)] in requirement order
        self.incoming: dict[str, list[tuple[str, str]]] = {}
        for uid, req in requirements.items():
            if req.get("deleted"):
                continue
            parent = req.get("parentId")
            if parent:
                self.children.setdefault(parent, []).append(uid)
            for rel in req.get("relationships") or []:
                target = relationship_target(rel)
                if target:
                    self.incoming.setdefault(target, []).append((uid, rel.get("type", "") if isinstance(rel, Mapping) else ""))

    def descendants(self, uid: str) -> list[str]:
        """Every live descendant of ``uid`` (cycle-safe), excluding ``uid`` itself."""
        seen = {uid}
        out: list[str] = []
        stack = list(self.children.get(uid, []))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            stack.extend(self.children.get(cur, []))
        return out

    def dependants(self, uid: str) -> list[str]:
        """Distinct sources that link to ``uid``, in requirement order."""
        return list(dict.fromkeys(src for src, _ in self.incoming.get(uid, [])))

    def downstream(self, uid: str, rel_types: Iterable[str]) -> list[tuple[str, str]]:
        """Breadth-first closure of sources that reach ``uid`` through ``rel_types``: ``[(uid, rel_type)]``."""
        wanted = set(rel_types)
        visited = {uid}
        out: list[tuple[str, str]] = []
        queue = deque([uid])
        while queue:
            current = queue.popleft()
            for src, rel_type in self.incoming.get(current, []):
                if src not in visited and rel_type in wanted:
                    visited.add(src)
                    out.append((src, rel_type))
                    queue.append(src)
        return out

    def suspect_closure(self, uid: str) -> list[tuple[str, str]]:
        """Breadth-first walk over every incoming link (any type) from ``uid``: ``[(source, linked_to)]``
        for each distinct source reached, where ``linked_to`` is the item it was reached from."""
        visited = {uid}
        order: list[tuple[str, str]] = []
        queue = deque([uid])
        while queue:
            current = queue.popleft()
            for src in self.dependants(current):
                if src == uid:
                    continue
                order.append((src, current))
                if src not in visited:
                    visited.add(src)
                    queue.append(src)
        return order
