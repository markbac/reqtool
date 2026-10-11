"""Principles by area and category: listing, the vocabulary, default packs and placing older principles."""

from __future__ import annotations

import builtins
from typing import Any, Mapping, Optional

from reqtool import principles as rules
from reqtool.store import Store
from .errors import Invalid, MissingItem


class PrincipleService:
    def __init__(self, store: Store) -> None:
        self.store = store

    # -- reading -----------------------------------------------------------------------------

    def list(self, area: Optional[str] = None, category: Optional[str] = None,
             status: Optional[str] = None, q: Optional[str] = None) -> list[dict[str, Any]]:
        items = [rules.with_placement(p) for p in self.store.live_principles()]
        if area:
            items = [p for p in items if (p.get("area") or rules.UNPLACED) == area]
        if category:
            items = [p for p in items if (p.get("category") or rules.GENERAL) == category]
        if status:
            items = [p for p in items if p.get("status") == status]
        if q:
            needle = q.lower()
            items = [p for p in items if needle in f"{p.get('id', '')} {p.get('title', '')}".lower()]
        return items

    def areas(self) -> dict[str, Any]:
        return rules.area_tree(self.store.live_principles(), self.store.principle_vocabulary())

    def vocabulary(self) -> dict[str, Any]:
        return {"vocabulary": self.store.principle_vocabulary(), "custom": bool(self.store.repo_enums.principle_areas)}

    def packs(self) -> builtins.list[dict[str, Any]]:
        have = {p.get("id") for p in self.store.principle_map().values()}
        out = []
        for area in rules.pack_areas():
            summary = rules.pack_summary(area)
            ids = {p["id"] for p in rules.load_pack(area)["principles"]}
            summary["installed"] = len(ids & have)
            summary["available"] = len(ids - have)
            out.append(summary)
        return out

    # -- changing ----------------------------------------------------------------------------

    def add_pack(self, area: str) -> dict[str, Any]:
        """Add a pack's principles. Ids already in the repository (even deleted ones) are left alone."""
        try:
            items = rules.pack_principles(area)
        except KeyError as exc:
            raise MissingItem(str(exc.args[0])) from None
        have = {p.get("id") for p in self.store.principle_map().values()}
        added = 0
        for item in items:
            if item["id"] not in have:
                self.store.create_principle(item)
                added += 1
        if self.store.repo_enums.principle_areas:
            self.store.save_principle_vocabulary(rules.merge_pack_into(self.store.principle_vocabulary(), area))
        return {"area": area, "added": added, "skipped": len(items) - added}

    def install_packs(self, areas: builtins.list[str]) -> dict[str, int]:
        """Add the chosen packs to a new repository and give it the matching vocabulary. Returns principles added per area."""
        counts = {area: self.add_pack(area)["added"] for area in areas}
        if areas:
            self.store.save_principle_vocabulary(rules.default_vocabulary(areas))
        return counts

    def set_vocabulary(self, vocabulary: Mapping[str, Any]) -> dict[str, Any]:
        try:
            saved = self.store.save_principle_vocabulary(dict(vocabulary))
        except ValueError as exc:
            raise Invalid(str(exc)) from None
        return {"vocabulary": saved, "custom": True}

    def place_existing(self) -> dict[str, Any]:
        """Give principles without an area and category one (from the default packs by id, else the old domain).

        Safe to run again: principles that already have both are not touched.
        """
        placed, left = 0, []
        for uid, p in list(self.store.principle_map().items()):
            if p.get("deleted") or p.get("area"):
                continue
            area, category = rules.placement(p)
            if not area:
                left.append(p.get("id", uid))
                continue
            self.store.update_principle(uid, {"area": area, "category": category}, summary=f"Placed in {area} > {category}.")
            placed += 1
        wrote_vocabulary = False
        if not self.store.repo_enums.principle_areas:
            used = sorted({p.get("area") for p in self.store.principle_map().values() if p.get("area")}, key=lambda a: _order(str(a)))
            known = [a for a in used if a in rules.pack_areas()]
            if known:
                self.store.save_principle_vocabulary(rules.default_vocabulary(known))
                wrote_vocabulary = True
        return {"placed": placed, "unplaced": left, "wrote_vocabulary": wrote_vocabulary}


def _order(area: str) -> int:
    order = rules.AREA_ORDER
    return order.index(area) if area in order else len(order)
