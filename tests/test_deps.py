import pytest
import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock
from reqtool.routers.deps import ConnectionManager, broadcast_sync, ws_manager

@pytest.mark.asyncio
async def test_connection_manager_connect_and_disconnect():
    cm = ConnectionManager()
    ws = AsyncMock()
    ws.accept = AsyncMock()
    
    await cm.connect(ws)
    assert ws in cm.active
    ws.accept.assert_called_once()

    cm.disconnect(ws)
    assert ws not in cm.active

@pytest.mark.asyncio
async def test_connection_manager_broadcast_prunes_dead():
    cm = ConnectionManager()
    ws_good = AsyncMock()
    ws_dead = AsyncMock()
    ws_dead.send_text.side_effect = Exception("Connection closed")

    cm.active.extend([ws_good, ws_dead])

    await cm.broadcast({"event": "test"})
    assert ws_good in cm.active
    assert ws_dead not in cm.active
    ws_good.send_text.assert_called_once()

@pytest.mark.asyncio
async def test_connection_manager_concurrent_access():
    cm = ConnectionManager()
    mock_sockets = [AsyncMock() for _ in range(20)]
    for ws in mock_sockets:
        ws.accept = AsyncMock()

    def _worker(start_idx):
        for i in range(start_idx, start_idx + 5):
            ws = mock_sockets[i]
            with cm._lock:
                cm.active.append(ws)

    threads = [threading.Thread(target=_worker, args=(i * 5,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(cm.active) == 20

@pytest.mark.asyncio
async def test_broadcast_sync_with_running_loop(monkeypatch):
    broadcast_mock = AsyncMock()
    monkeypatch.setattr(ws_manager, "broadcast", broadcast_mock)
    
    broadcast_sync("test_event", {"data": "sample"})
    await asyncio.sleep(0.01)
    broadcast_mock.assert_called_once_with({"event": "test_event", "data": "sample"})
