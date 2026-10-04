"""
reqtool.features.notifications
==============================
Mentions, review requests and status changes as an inbox plus Slack or Teams text (FEAT-10).
Preferences are per user in ``.reqtool/notification_prefs.yaml``; the inbox is ``.reqtool/inbox.yaml``.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from reqtool.fileio import load_yaml, save_yaml, utcnow_iso

NOTIFY_EVENTS = ("mention", "review_requested", "status_changed")
MENTION = re.compile(r"(?<![\w@])@([A-Za-z0-9][A-Za-z0-9_.-]{0,63})")
INBOX_LIMIT = 500


def mentions(text: str) -> list[str]:
    return list(dict.fromkeys(MENTION.findall(text or "")))


def describe(event: str, payload: dict) -> str:
    """One line of plain text for chat webhooks and the inbox."""
    label = payload.get("id") or payload.get("uid", "")
    if event == "mention":
        return f"{payload.get('by', 'Someone')} mentioned @{payload.get('user', '')} on {label}"
    if event == "review_requested":
        return f"{payload.get('by', 'Someone')} asked {payload.get('reviewer', '')} to review {label}"
    if event == "status_changed":
        return f"{label} moved from {payload.get('old_status', '?')} to {payload.get('new_status', payload.get('status', '?'))}"
    if event in ("requirement_approved", "approved"):
        return f"{label} was approved by {payload.get('approved_by', '')}"
    return f"{event.replace('_', ' ')}: {label}"


def chat_body(fmt: str, event: str, payload: dict) -> dict | None:
    """The JSON body for a ``slack`` or ``teams`` webhook (both accept ``{"text": ...}``); None for plain json."""
    if fmt in ("slack", "teams"):
        return {"text": describe(event, payload)}
    return None


def _prefs_path(store):
    return store.root / ".reqtool" / "notification_prefs.yaml"


def get_prefs(store, user: str) -> dict[str, Any]:
    default = {"events": list(NOTIFY_EVENTS), "muted": False}
    path = _prefs_path(store)
    if not path.exists():
        return default
    try:
        return {**default, **(load_yaml(path).get(user) or {})}
    except Exception:
        return default


def set_prefs(store, user: str, events: list[str], muted: bool) -> dict[str, Any]:
    unknown = [e for e in events if e not in NOTIFY_EVENTS]
    if unknown:
        raise ValueError("Unknown notification event(s): " + ", ".join(unknown))
    with store.lock:
        path = _prefs_path(store)
        data = load_yaml(path) if path.exists() else {}
        data[user] = {"events": events, "muted": bool(muted)}
        save_yaml(path, data)
    return data[user]


def _inbox_path(store):
    return store.root / ".reqtool" / "inbox.yaml"


def _load_inbox(store) -> list[dict]:
    path = _inbox_path(store)
    if not path.exists():
        return []
    try:
        return list(load_yaml(path).get("items", []))
    except Exception:
        return []


def recipients(store, event: str, payload: dict) -> list[str]:
    if event == "mention":
        return [payload["user"]] if payload.get("user") else []
    if event == "review_requested":
        return [payload["reviewer"]] if payload.get("reviewer") else []
    if event == "status_changed":
        owner = (store.requirements.get(payload.get("uid", "")) or {}).get("owner")
        return [owner] if owner else []
    return []


def deliver(store, event: str, payload: dict) -> None:
    """Event subscriber: add inbox entries for the recipients who have not opted out."""
    if event not in NOTIFY_EVENTS:
        return
    users = [u for u in recipients(store, event, payload) if u != payload.get("by")]
    if not users:
        return
    with store.lock:
        items = _load_inbox(store)
        for user in users:
            prefs = get_prefs(store, user)
            if prefs["muted"] or event not in prefs["events"]:
                continue
            items.append({"id": uuid.uuid4().hex[:12], "to": user, "event": event, "uid": payload.get("uid", ""),
                          "text": describe(event, payload), "at": utcnow_iso(), "read": False})
        save_yaml(_inbox_path(store), {"items": items[-INBOX_LIMIT:]})


def inbox(store, user: str, unread_only: bool = False) -> list[dict]:
    return [i for i in reversed(_load_inbox(store)) if i["to"] == user and not (unread_only and i["read"])]


def mark_read(store, user: str, item_id: str) -> bool:
    with store.lock:
        items = _load_inbox(store)
        for i in items:
            if i["id"] == item_id and i["to"] == user:
                i["read"] = True
                save_yaml(_inbox_path(store), {"items": items})
                return True
    return False
