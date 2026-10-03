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

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time event stream & multi-user CRDT co-editing channel."""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")
                if msg_type in ("PRESENCE", "CURSOR", "LOCK_FIELD", "UNLOCK_FIELD", "CO_EDIT"):
                    await ws_manager.broadcast({"event": msg_type, "payload": msg.get("payload", {})})
            except Exception:
                log.debug("Ignoring malformed WebSocket message", exc_info=True)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
