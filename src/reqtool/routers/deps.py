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

    async def connect(self, ws: WebSocket):
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
    import asyncio
    msg = {"event": event, **payload}
    async def _do():
        await ws_manager.broadcast(msg)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        loop.create_task(_do())


from concurrent.futures import ThreadPoolExecutor

_webhook_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="reqtool-webhook-")


def fire_webhook(store: Store, event: str, payload: dict) -> None:
    """Fire webhooks and broadcast WebSocket notification async."""
    # 1. HTTP Webhooks
    hooks = [w for w in store.config.webhooks if w.enabled and event in w.events]
    if hooks:
        body = _json.dumps({
            "event": event,
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
                    "X-Reqtool-Event": event,
                }
                if secret:
                    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                    headers["X-Reqtool-Signature"] = f"sha256={sig}"
                httpx.post(url, content=body, headers=headers, timeout=5, follow_redirects=False)
            except Exception as exc:
                log.warning("Webhook delivery failed to %s: %s", url, exc)

        for hook in hooks:
            _webhook_executor.submit(_send, hook.url, hook.secret)

    # 2. WebSocket broadcast
    broadcast_sync(event, {"uid": payload.get("uid", ""), "payload": payload})
