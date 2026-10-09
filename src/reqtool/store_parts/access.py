"""How code outside the store reads (and, rarely, changes) what it holds (ARC-02).

The collections are plain dicts today. Nothing outside ``store.py`` and ``store_parts/`` touches them: it asks
for a read-only view or a list, so changing how artefacts are kept touches this file and not 17 others.
``tests/unit/test_store_encapsulation.py`` fails when a module reaches in again.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from ._host import StoreHost

Artefact = dict[str, Any]


class AccessMixin(StoreHost):
    # Read-only views, keyed by uid (requirements, principles, decisions) or id (modules, products).
    def requirement_map(self) -> Mapping[str, Artefact]:
        return MappingProxyType(self.requirements)

    def principle_map(self) -> Mapping[str, Artefact]:
        return MappingProxyType(self.principles)

    def decision_map(self) -> Mapping[str, Artefact]:
        return MappingProxyType(self.decisions)

    def module_map(self) -> Mapping[str, Artefact]:
        return MappingProxyType(self.modules)

    def product_map(self) -> Mapping[str, Artefact]:
        return MappingProxyType(self.products)

    def module_requirement_map(self) -> Mapping[str, Mapping[str, Artefact]]:
        """``{module_id: {uid: requirement}}`` for the requirements that belong to shared modules."""
        return MappingProxyType(self.module_requirements)

    # The same collections without soft-deleted items.
    def live_requirements(self) -> list[Artefact]:
        return [r for r in self.requirements.values() if not r.get("deleted")]

    def live_principles(self) -> list[Artefact]:
        return [p for p in self.principles.values() if not p.get("deleted")]

    def live_decisions(self) -> list[Artefact]:
        return [d for d in self.decisions.values() if not d.get("deleted")]

    # The few places that change the collections without going through a create/update method.
    def register_product(self, product_id: str, product: Artefact) -> None:
        """Make a product that has just been written to disk known to the store."""
        with self._lock:
            self.products[product_id] = product

    def forget_requirement(self, uid: str) -> None:
        """Drop a requirement from memory only (an import that failed part-way removes its file itself)."""
        with self._lock:
            self.requirements.pop(uid, None)
