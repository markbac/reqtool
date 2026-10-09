"""UID and text search across artefacts."""

from __future__ import annotations

from typing import Any

from reqtool.store_parts._host import StoreHost



class SearchMixin(StoreHost):
    def search_uids(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search requirements, principles, and TBDs by ID or title fragment."""
        q = query.lower().strip()
        results = []
        for uid, req in self.requirements.items():
            if req.get("deleted"):
                continue
            if q in req.get("id", "").lower() or q in req.get("title", "").lower():
                results.append({
                    "uid": uid,
                    "id": req.get("id", ""),
                    "title": req.get("title", ""),
                    "type": "requirement",
                })
        for uid, p in self.principles.items():
            if p.get("deleted"):
                continue
            if q in p.get("id", "").lower() or q in p.get("title", "").lower():
                results.append({
                    "uid": uid,
                    "id": p.get("id", ""),
                    "title": p.get("title", ""),
                    "type": "principle",
                })
        for uid, d in self.decisions.items():
            if d.get("deleted"):
                continue
            if q in d.get("id", "").lower() or q in d.get("title", "").lower():
                results.append({
                    "uid": uid,
                    "id": d.get("id", ""),
                    "title": d.get("title", ""),
                    "type": "tbd" if d.get("type") == "tbd" else "decision",
                })
        return results[:limit]
