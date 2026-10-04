"""
reqtool.events
==============
The one event catalogue and publisher. Every mutating endpoint publishes exactly one
event; webhooks, WebSocket clients and automation rules are subscribers.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger(__name__)

# canonical event id -> description
CATALOGUE: dict[str, str] = {
    "requirement_created": "A requirement was created (or cloned).",
    "requirement_updated": "A requirement's content changed without a status change.",
    "requirement_deleted": "A requirement was deleted.",
    "requirement_approved": "A requirement was approved.",
    "status_changed": "A requirement's status changed (by edit, bulk edit or transition).",
    "comment_added": "A comment was added to a requirement.",
    "attachment_added": "An attachment was added to a requirement.",
    "mention": "A user was @mentioned in a comment.",
    "review_requested": "A review of a requirement was requested from a user.",
}

# Names sent on the wire (webhook body, WebSocket frame) and accepted in webhook
# subscriptions for events that predate the catalogue.
WIRE_NAMES: dict[str, str] = {"requirement_approved": "approved"}


def wire_name(event: str) -> str:
    return WIRE_NAMES.get(event, event)


def subscription_matches(subscribed: list[str], event: str) -> bool:
    """True if a webhook's ``events`` list selects ``event`` (canonical or wire name)."""
    return event in subscribed or wire_name(event) in subscribed


Subscriber = Callable[[Any, str, dict], None]


class EventPublisher:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> Subscriber:
        if fn not in self._subscribers:
            self._subscribers.append(fn)
        return fn

    def publish(self, store: Any, event: str, payload: dict) -> None:
        if event not in CATALOGUE:
            raise ValueError(f"unknown event '{event}'")
        for sub in list(self._subscribers):
            try:
                sub(store, event, payload)
            except Exception:  # one failing subscriber must not break the request or the others
                log.warning("Event subscriber %s failed for %s", getattr(sub, "__name__", sub), event, exc_info=True)


publisher = EventPublisher()
