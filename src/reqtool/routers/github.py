"""
reqtool.routers.github
======================
REST API router for GitHub webhook ingestion and development repo linking.
"""

from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from reqtool.store import Store
from reqtool.github_sync import process_github_push_event
from reqtool.routers.deps import get_store

router = APIRouter(prefix="/webhooks/github", tags=["integrations"])


@router.post("")
async def github_webhook_handler(
    request: Request,
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    store: Store = Depends(get_store),
):
    """Receive and process GitHub webhook events (push, pull_request, issues)."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = x_github_event or "push"
    linked_commits = []

    if event_type == "push":
        linked_commits = process_github_push_event(store, payload)

    return {
        "status": "ok",
        "event": event_type,
        "processed_links": len(linked_commits),
        "details": linked_commits,
    }
