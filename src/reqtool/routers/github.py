"""
reqtool.routers.github
======================
REST API router for GitHub webhook ingestion and development repo linking.
"""

import hashlib
import hmac
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from reqtool.store import Store
from reqtool.github_sync import process_github_push_event
from reqtool.routers.deps import get_store

router = APIRouter(prefix="/webhooks/github", tags=["integrations"])


def _verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.strip())


@router.post("")
async def github_webhook_handler(
    request: Request,
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    store: Store = Depends(get_store),
):
    """Receive and process GitHub webhook events (push, pull_request, issues).

    Requires ``REQTOOL_GITHUB_WEBHOOK_SECRET`` and a valid ``X-Hub-Signature-256``.
    """
    secret = os.environ.get("REQTOOL_GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail={
            "error": "not_configured",
            "message": "GitHub webhook is disabled: set REQTOOL_GITHUB_WEBHOOK_SECRET to enable it"})
    raw = await request.body()
    if not _verify_signature(secret, raw, x_hub_signature_256):
        raise HTTPException(status_code=401, detail={
            "error": "unauthorized", "message": "Missing or invalid X-Hub-Signature-256"})
    try:
        import json
        payload = json.loads(raw)
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
