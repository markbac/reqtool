"""
reqtool.routers.git_ops
=======================
FastAPI router for Git operations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from reqtool.store import Store
from reqtool.models import CommitRequest
from reqtool.git_ops import (
    has_conflicts, is_git_repo, stage_file, commit as git_commit, git_status, git_log, NothingToCommit, attribution)
from reqtool.identity import MissingIdentity, with_trailers
from reqtool import sync
from .deps import get_store, not_found, conflict

log = logging.getLogger(__name__)

router = APIRouter(tags=["git"])


@router.get("/git/status")
def get_git_status(store: Store = Depends(get_store)):
    out: dict = git_status(store.root)
    if is_git_repo(store.root):
        out["sync"] = sync.status(store.root)
    return out


def _sync_call(fn):
    try:
        return fn()
    except sync.SyncError as exc:
        status = 502 if exc.code in ("git_error", "timeout") else 409
        raise HTTPException(status_code=status, detail={"error": exc.code, "message": str(exc)})


@router.post("/git/fetch")
def git_fetch(store: Store = Depends(get_store)):
    """Fetch from the remote (#348). Nothing in the working tree changes."""
    return _sync_call(lambda: sync.fetch(store.root))


@router.post("/git/pull")
def git_pull(store: Store = Depends(get_store)):
    """Bring in the upstream's commits, reload, and report what validation finds."""
    return _sync_call(lambda: sync.pull_store(store))


@router.post("/git/push")
def git_push(store: Store = Depends(get_store)):
    return _sync_call(lambda: sync.push(store.root))


@router.post("/git/sync")
def git_sync(body: Optional[dict] = None, store: Store = Depends(get_store)):
    """Fetch, pull, reload and validate, then push (unless ``{"push": false}``)."""
    push_changes = bool((body or {}).get("push", True))
    return _sync_call(lambda: sync.sync_store(store, push_changes))


@router.post("/git/commit")
def batch_commit(body: CommitRequest, store: Store = Depends(get_store)):
    """Commit the listed items, one commit per author (#347). With no ``uids``, commit what is already staged."""
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    paths = [p for p in (_artefact_path(store, uid) for uid in body.uids) if p is not None]
    try:
        if body.uids:
            groups: dict[tuple, list[Path]] = {}
            for p in paths:
                who = attribution(store, [p])
                groups.setdefault((who.author, who.committer, tuple(who.trailers)), []).append(p)
        else:
            staged = [store.root / f for f in git_status(store.root)["staged"]]
            who = attribution(store, [p for p in staged if p.suffix == ".yaml" and p.exists()])
            groups = {(who.author, who.committer, tuple(who.trailers)): []}
    except MissingIdentity as exc:
        raise HTTPException(status_code=409, detail={"error": "no_git_identity", "message": str(exc)})
    if not groups:
        raise conflict("Nothing staged to commit")
    try:
        shas = []
        for (author, committer, trailers), group in groups.items():
            for p in group:
                stage_file(store.root, p)
            shas.append(git_commit(
                store.root, with_trailers(body.message, list(trailers)), author.name, author.email,
                paths=group or None, committer_name=committer.name, committer_email=committer.email,
                sign=store.config.git.sign_commits))
        return {"commit_sha": shas[-1], "commits": shas}
    except NothingToCommit as exc:
        raise conflict(str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})


def _artefact_path(store: Store, uid: str) -> Optional[Path]:
    for get_path in (store.req_path, store.principle_path, store.decision_path):
        p = get_path(uid)
        if p.exists():
            return p
    return None


@router.get("/git/log/{uid}")
def get_git_log(uid: str, store: Store = Depends(get_store)):
    for get_path in (store.req_path, store.principle_path, store.decision_path):
        p = get_path(uid)
        if p.exists():
            return git_log(store.root, p)
    raise not_found(uid)
