"""
reqtool.routers.deps
===================
Shared dependencies, store accessor, webhook dispatcher, and WebSocket connection manager.
"""

from __future__ import annotations

import logging
import json as _json
import threading
from typing import Annotated, Optional
from fastapi import Depends, Request, WebSocket, HTTPException

from reqtool import __version__
from reqtool.git_ops import has_conflicts, stage_file, unstage_file, commit as git_commit
from reqtool.store import Store
from reqtool.events import publisher, wire_name, subscription_matches
from reqtool.automation import automation_subscriber

log = logging.getLogger(__name__)


def get_store(request: Request) -> Store:
    return request.app.state.store


def canonical_uid(uid: str, request: Request) -> str:
    """A requirement route's ``{uid}`` accepts either the UID or the human ID (for example ``FR-042``)."""
    return request.app.state.store.resolve_uid(uid) or uid


ReqUid = Annotated[str, Depends(canonical_uid)]


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


def commit_message(body) -> str:
    """The commit message, or a 422 before anything is changed (git would reject an empty one)."""
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail={"error": "validation", "message": "A commit message is required"})
    return message


def commit_artefact(store: Store, body, path, *, bump, undo, version) -> dict:
    """Bump the version, stage and commit ONLY ``path``, and undo the bump if git fails (ARC-16).

    ``bump(message)`` records the version and history entry, ``undo()`` reverses it and ``version()``
    reads the new version. Nothing is written after the commit, so the working tree stays clean and
    the SHA lives in git history.
    """
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    message = commit_message(body)
    try:
        bump(message)
        stage_file(store.root, path)
        sha = git_commit(store.root, message, store.config.git.commit_name,
                         store.config.git.commit_email, paths=[path])
        return {"commit_sha": sha, "version": version()}
    except RuntimeError as exc:
        undo()
        unstage_file(store.root, path)
        raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})


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


def check_webhook_target(url: str, allow_private: bool = False) -> Optional[str]:
    """Return a reason string if ``url`` must not be called, else None.

    Resolves the hostname and rejects loopback, private, link-local, reserved and
    multicast addresses (any of the resolved ones) unless ``allow_private``.
    Called immediately before each delivery.
    """
    import ipaddress, socket
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "only http(s) URLs with a host are allowed"
    if parsed.hostname.lower() in ("metadata.google.internal",):
        return "cloud metadata host is blocked"
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except OSError as exc:
        return f"host does not resolve ({exc})"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_link_local or str(ip).startswith("169.254."):
            return f"address {ip} is link-local (cloud metadata range) and is always blocked"
        if not allow_private and (ip.is_private or ip.is_loopback or ip.is_reserved
                                  or ip.is_multicast or ip.is_unspecified):
            return f"address {ip} is not public (set allow_private on the webhook to permit it)"
    return None


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

    def _send(url: str, secret: Optional[str], allow_private: bool = False) -> None:
        try:
            import httpx, hashlib, hmac
            reason = check_webhook_target(url, allow_private)
            if reason:
                log.warning("Webhook to %s blocked: %s", url, reason)
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
        _webhook_executor.submit(_send, hook.url, hook.secret, hook.allow_private)


def _ws_subscriber(store: Store, event: str, payload: dict) -> None:
    broadcast_sync(wire_name(event), {"uid": payload.get("uid", ""), "payload": payload})


publisher.subscribe(_webhook_subscriber)
publisher.subscribe(_ws_subscriber)
publisher.subscribe(automation_subscriber)


def publish_event(store: Store, event: str, payload: dict) -> None:
    """Publish a catalogue event to all subscribers (webhooks, WebSocket, automation)."""
    publisher.publish(store, event, payload)
