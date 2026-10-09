"""Typing helper for the ``Store`` mixins.

The mixins call attributes that ``Store`` provides (``requirements``, ``graph``, ``root``, ...). For the
type checker, any attribute not declared on a mixin is treated as supplied by the host class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


class StoreHost:
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
