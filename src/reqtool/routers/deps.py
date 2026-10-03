"""
reqtool.routers.deps
===================
Shared dependencies, store accessor, webhook dispatcher, and WebSocket connection manager.
"""

from __future__ import annotations

import logging
import json as _json
import threading
from typing import Optional
from fastapi import Request, WebSocket, HTTPException

from reqtool import __version__
from reqtool.store import Store
from reqtool.events import publisher, wire_name, subscription_matches

log = logging.getLogger(__name__)


def get_store(request: Request) -> Store:
    return request.app.state.store


def not_found(uid: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": "not_found", "message": f"UID '{uid}' not found", "uid": uid},
    )


def conflict(msg: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": "conflict", "message": msg},
    )


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self._lock = threading.RLock()
        # The server's event loop, captured when the first socket connects, so
        # synchronous handlers (which run in worker threads) can schedule sends.
        self.loop = None

    async def connect(self, ws: WebSocket):
        import asyncio
        self.loop = asyncio.get_running_loop()
        await ws.accept()
        with self._lock:
            self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        with self._lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, message: dict):
        text = _json.dumps(message)
        with self._lock:
            connections = list(self.active)
        dead = []
        for ws in connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        if dead:
            with self._lock:
                for ws in dead:
                    if ws in self.active:
                        self.active.remove(ws)


ws_manager = ConnectionManager()


def broadcast_sync(event: str, payload: dict) -> None:
    """Broadcast to WebSocket clients from sync or async code.

    Sync route handlers run in a worker thread with no running loop, so the
    send is scheduled onto the server loop captured in ConnectionManager.connect.
    """
    import asyncio
    msg = {"event": event, **payload}
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        running.create_task(ws_manager.broadcast(msg))
        return
    loop = ws_manager.loop
    if loop is None or loop.is_closed() or not ws_manager.active:
        return
    fut = asyncio.run_coroutine_threadsafe(ws_manager.broadcast(msg), loop)
    fut.add_done_callback(lambda f: f.exception() and log.warning("WS broadcast failed: %s", f.exception()))


from concurrent.futures import ThreadPoolExecutor

_webhook_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="reqtool-webhook-")


def _webhook_subscriber(store: Store, event: str, payload: dict) -> None:
    """Deliver the event to matching outbound HTTP webhooks."""
    hooks = [w for w in store.config.webhooks if w.enabled and subscription_matches(w.events, event)]
    if not hooks:
        return
    wire = wire_name(event)
    body = _json.dumps({
        "event": wire,
        "repo_id": store.config.repo_id,
        "payload": payload,
    }).encode()

    def _send(url: str, secret: Optional[str]) -> None:
        try:
            import httpx, hashlib, hmac
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                log.warning("Invalid webhook URL scheme for %s", url)
                return
            if parsed.hostname in ("169.254.169.254", "metadata.google.internal"):
                log.warning("Blocked potential SSRF webhook URL: %s", url)
                return

            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"reqtool/{__version__}",
                "X-Reqtool-Event": wire,
            }
            if secret:
                sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                headers["X-Reqtool-Signature"] = f"sha256={sig}"
            httpx.post(url, content=body, headers=headers, timeout=5, follow_redirects=False)
        except Exception as exc:
            log.warning("Webhook delivery failed to %s: %s", url, exc)

    for hook in hooks:
        _webhook_executor.submit(_send, hook.url, hook.secret)


def _ws_subscriber(store: Store, event: str, payload: dict) -> None:
    broadcast_sync(wire_name(event), {"uid": payload.get("uid", ""), "payload": payload})


publisher.subscribe(_webhook_subscriber)
publisher.subscribe(_ws_subscriber)


def publish_event(store: Store, event: str, payload: dict) -> None:
    """Publish a catalogue event to all subscribers (webhooks, WebSocket, automation)."""
    publisher.publish(store, event, payload)
