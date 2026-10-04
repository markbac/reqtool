"""
reqtool.watcher
===============
File watcher that keeps the in-memory store in step with edits made outside the API
(a text editor, ``git checkout``, a pull). It follows ``store.root``, so it is restarted
when the repository is switched.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

WATCHED_DIRS = ("requirements", "principles", "decisions", "tbds", "modules", "products", ".reqtool")


def make_handler(store: Any):
    from watchdog.events import FileSystemEventHandler

    class ReloadHandler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory or not str(event.src_path).endswith(".yaml"):
                return
            # An exception escaping a watchdog handler kills the observer thread, so no later
            # change would ever be seen: log it and carry on.
            try:
                changed = Path(event.src_path)
                log.debug("File changed: %s", changed)
                store.reload_file(changed)
            except Exception:
                log.exception("Could not reload %s", event.src_path)

    return ReloadHandler()


def start_watcher(store: Any) -> Optional[Any]:
    """Start watching ``store.root``. Returns the observer, or None when it cannot start."""
    try:
        from watchdog.observers import Observer
        observer = Observer()
        handler = make_handler(store)
        for subdir in WATCHED_DIRS:
            watch_path = Path(store.root) / subdir
            watch_path.mkdir(parents=True, exist_ok=True)
            observer.schedule(handler, str(watch_path), recursive=True)
        observer.daemon = True
        observer.start()
        log.info("File watcher started for %s (incremental reload)", store.root)
        return observer
    except Exception as exc:
        log.warning("File watcher not started: %s", exc)
        return None


def stop_watcher(observer: Optional[Any]) -> None:
    if observer is None:
        return
    try:
        observer.stop()
        observer.join(timeout=2)
    except Exception:
        log.debug("Stopping the file watcher failed", exc_info=True)


def restart_watcher(app: Any, store: Any) -> None:
    """Point the watcher at the store's current root (call after switching repository).

    Does nothing when the application was created without a watcher."""
    if getattr(app.state, "watcher", None) is None:
        return
    stop_watcher(app.state.watcher)
    app.state.watcher = start_watcher(store)
