"""
reqtool.routers.ws
==================
FastAPI router for WebSocket endpoints.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .deps import ws_manager

log = logging.getLogger(__name__)

router = APIRouter()


import json

MAX_WS_MESSAGE_CHARS = 64 * 1024
RELAYED_TYPES = ("PRESENCE", "CURSOR", "LOCK_FIELD", "UNLOCK_FIELD", "CO_EDIT")

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time event stream & multi-user CRDT co-editing channel."""
    from reqtool import security
    if not security.websocket_allowed(websocket, websocket.app.state.auth_mode, websocket.app.state.store.root):
        # 4401: login required / token rejected, 4403: not a local connection
        await websocket.close(code=4401 if websocket.app.state.auth_mode == "required" else 4403)
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > MAX_WS_MESSAGE_CHARS:
                await websocket.close(code=1009)  # message too big
                break
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")
                payload = msg.get("payload", {})
                if msg_type in RELAYED_TYPES and isinstance(payload, dict):
                    await ws_manager.broadcast({"event": msg_type, "payload": payload})
            except Exception:
                log.debug("Ignoring malformed WebSocket message", exc_info=True)
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)
