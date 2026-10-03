"""
reqtool.api
===========
FastAPI application entry point.
Assembles APIRouters from reqtool.routers into the application.
OpenAPI 3.1 spec is generated automatically at GET /openapi.json.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

from . import __version__
from .store import Store
from .fileio import InvalidId
from .git_ops import InvalidRef
from .store import ParentCycle
from .routers import (
    system, requirements, principles, decisions, tbds, modules,
    comments, attachments, analysis, exports, git_ops,
    imports, ws, auth, iterations, github, automation,
)

log = logging.getLogger(__name__)

# http(s)://localhost, 127.0.0.1 or [::1] on any port.
LOCAL_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"


def create_app(repo_root: Path, auth_mode: str | None = None) -> FastAPI:
    store = Store(repo_root)
    store.load()

    app = FastAPI(
        title="reqtool",
        version=__version__,
        description=(
            "Git-backed YAML requirements management tool. "
            "Requirements, principles, and TBDs live as individual YAML files; "
            "the API handles hashing, versioning, validation, and export."
        ),
        license_info={"name": "MIT"},
        contact={"name": "reqtool"},
    )

    app.state.store = store

    try:
        from .auth import UserStore
        if UserStore(store.root).has_default_credentials():
            log.warning(
                "SECURITY: this repository still has the legacy default admin account "
                "(admin / admin123). Logins with it are refused; run `req user passwd admin`."
            )
    except Exception:  # never block start-up on this check
        pass

    # Access control is registered BEFORE CORS because the last middleware added
    # is the outermost: CORS must wrap it so preflights and 401/403 replies still
    # carry CORS headers for the allowed local origins.
    from . import security
    security.install(app, security.resolve_mode(auth_mode))

    # Only the local UI (and any origins the operator lists) may call the API
    # from a browser. A wildcard lets any web page the user visits drive the API.
    extra_origins = [o.strip() for o in os.environ.get("REQTOOL_CORS_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=extra_origins,
        allow_origin_regex=LOCAL_ORIGIN_REGEX,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "If-Match"],
    )

    # ------------------------------------------------------------------
    # File watcher -- disabled under pytest to prevent inotify fd leaks
    # ------------------------------------------------------------------
    _under_test = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ

    if not _under_test:
        try:
            import threading
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class ReloadHandler(FileSystemEventHandler):
                def __init__(self):
                    super().__init__()
                    self._last_events = {}
                    self._lock = threading.Lock()

                def on_any_event(self, event):
                    if event.is_directory:
                        return
                    if event.src_path.endswith(".yaml"):
                        import time
                        now = time.time()
                        with self._lock:
                            last_time = self._last_events.get(event.src_path, 0)
                            if now - last_time < 0.1:  # 100ms debounce
                                return
                            self._last_events[event.src_path] = now
                        changed = Path(event.src_path)
                        log.debug("File changed (debounced): %s", changed)
                        store.reload_file(changed)

            observer = Observer()
            for subdir in ("requirements", "principles", "decisions", "tbds", "modules", "products", ".reqtool"):
                watch_path = repo_root / subdir
                watch_path.mkdir(parents=True, exist_ok=True)
                observer.schedule(ReloadHandler(), str(watch_path), recursive=True)
            observer.start()
            log.info("File watcher started (incremental reload)")
        except Exception as exc:
            log.warning("File watcher not started: %s", exc)

    # ------------------------------------------------------------------
    # Include APIRouters
    # ------------------------------------------------------------------
    @app.exception_handler(InvalidId)
    @app.exception_handler(InvalidRef)
    async def _invalid_input_handler(request, exc):
        return JSONResponse(status_code=422, content={"detail": {"error": "validation", "message": str(exc)}})

    @app.exception_handler(ParentCycle)
    async def _parent_cycle_handler(request, exc):
        return JSONResponse(status_code=409, content={"detail": {"error": "parent_cycle", "message": str(exc)}})

    app.include_router(system.router)
    app.include_router(requirements.router)
    app.include_router(principles.router)
    app.include_router(decisions.router)
    app.include_router(tbds.router)
    app.include_router(modules.router)
    app.include_router(comments.router)
    app.include_router(attachments.router)
    app.include_router(analysis.router)
    app.include_router(exports.router)
    app.include_router(git_ops.router)
    app.include_router(imports.router)
    app.include_router(ws.router)
    app.include_router(auth.router)
    app.include_router(iterations.router)
    app.include_router(github.router)
    app.include_router(automation.router)

    # ------------------------------------------------------------------
    # Static UI (or fallback landing page when dist is not built)
    # ------------------------------------------------------------------
    ui_dist = Path(__file__).parent / "ui" / "dist"
    if ui_dist.exists():
        app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="ui")
    else:
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def landing():
            """Fallback landing page served when the React UI has not been built."""
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>reqtool {__version__}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0d1117; color: #e6edf3; min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
    }}
    .card {{
      background: #161b22; border: 1px solid #30363d; border-radius: 12px;
      padding: 40px; max-width: 520px; width: 100%; text-align: center;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }}
    .logo {{ font-size: 2.5rem; font-weight: 700; color: #58a6ff; margin-bottom: 8px; }}
    .ver  {{ font-size: 0.85rem; color: #8b949e; margin-bottom: 24px; }}
    p     {{ font-size: 0.95rem; color: #c9d1d9; line-height: 1.5; margin-bottom: 24px; }}
    .links {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }}
    a.btn {{
      display: inline-block; padding: 10px 20px; border-radius: 6px;
      font-size: 0.9rem; font-weight: 600; text-decoration: none;
      transition: background 0.15s ease;
    }}
    a.primary {{ background: #238636; color: #fff; }}
    a.primary:hover {{ background: #2ea043; }}
    a.secondary {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }}
    a.secondary:hover {{ background: #30363d; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">reqtool</div>
    <div class="ver">v{__version__} &bull; API Server Running</div>
    <p>
      The API server is online. To enable the web UI, build the frontend:
      <br><code style="color:#f0883e">cd src/reqtool/ui &amp;&amp; npm run build</code>
    </p>
    <div class="links">
      <a href="/docs" class="btn primary">OpenAPI Docs (/docs)</a>
      <a href="/redoc" class="btn secondary">ReDoc (/redoc)</a>
      <a href="/openapi.json" class="btn secondary">JSON Spec</a>
    </div>
  </div>
</body>
</html>"""
            return HTMLResponse(content=html)
    # ------------------------------------------------------------------
    # Custom OpenAPI Schema (Security schemes & OpenAPI 3.1 Webhooks)
    # ------------------------------------------------------------------
    from fastapi.openapi.utils import get_openapi

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title="reqtool",
            version=__version__,
            description=(
                "Git-backed YAML requirements management tool. "
                "Requirements, principles, and TBDs live as individual YAML files; "
                "the API handles hashing, versioning, validation, and export."
            ),
            routes=app.routes,
        )
        openapi_schema["components"]["securitySchemes"] = {
            "HTTPBearer": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT Bearer token acquired via POST /auth/login",
            },
            "APIKeyHeader": {
                "type": "apiKey",
                "name": "X-API-Key",
                "in": "header",
                "description": "API key passed in X-API-Key header",
            },
        }
        openapi_schema["security"] = [
            {"HTTPBearer": []},
            {"APIKeyHeader": []},
        ]
        openapi_schema["webhooks"] = {
            "requirement_created": {
                "post": {
                    "summary": "Outbound event fired when a requirement is created",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "event": {"type": "string", "example": "requirement_created"},
                                        "repo_id": {"type": "string"},
                                        "payload": {
                                            "type": "object",
                                            "properties": {
                                                "uid": {"type": "string"},
                                                "id": {"type": "string"},
                                                "title": {"type": "string"},
                                            },
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Webhook acknowledged"}},
                }
            },
            "requirement_updated": {
                "post": {
                    "summary": "Outbound event fired when a requirement is updated",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "event": {"type": "string", "example": "requirement_updated"},
                                        "repo_id": {"type": "string"},
                                        "payload": {
                                            "type": "object",
                                            "properties": {
                                                "uid": {"type": "string"},
                                                "id": {"type": "string"},
                                            },
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Webhook acknowledged"}},
                }
            },
            "requirement_approved": {
                "post": {
                    "summary": "Outbound event fired when a requirement is approved",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "event": {"type": "string", "example": "requirement_approved"},
                                        "repo_id": {"type": "string"},
                                        "payload": {
                                            "type": "object",
                                            "properties": {
                                                "uid": {"type": "string"},
                                                "approved_by": {"type": "string"},
                                            },
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Webhook acknowledged"}},
                }
            },
            "attachment_added": {
                "post": {
                    "summary": "Outbound event fired when a file attachment is uploaded",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "event": {"type": "string", "example": "attachment_added"},
                                        "repo_id": {"type": "string"},
                                        "payload": {
                                            "type": "object",
                                            "properties": {
                                                "uid": {"type": "string"},
                                                "filename": {"type": "string"},
                                            },
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Webhook acknowledged"}},
                }
            },
            "comment_added": {
                "post": {
                    "summary": "Outbound event fired when a discussion comment is posted",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "event": {"type": "string", "example": "comment_added"},
                                        "repo_id": {"type": "string"},
                                        "payload": {
                                            "type": "object",
                                            "properties": {
                                                "uid": {"type": "string"},
                                                "comment_uid": {"type": "string"},
                                            },
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Webhook acknowledged"}},
                }
            },
        }
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi
    return app
