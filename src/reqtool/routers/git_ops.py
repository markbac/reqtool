"""
reqtool.routers.git_ops
=======================
FastAPI router for Git operations.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException

from reqtool.store import Store
from reqtool.models import CommitRequest
from reqtool.git_ops import has_conflicts, stage_file, commit as git_commit, git_status, git_log, NothingToCommit
from .deps import get_store, not_found, conflict

log = logging.getLogger(__name__)

router = APIRouter(tags=["git"])


@router.get("/git/status")
def get_git_status(store: Store = Depends(get_store)):
    return git_status(store.root)


@router.post("/git/commit")
def batch_commit(body: CommitRequest, store: Store = Depends(get_store)):
    if has_conflicts(store.root):
        raise conflict("Working tree has unresolved merge conflicts")
    try:
        for uid in body.uids:
            for get_path in (store.req_path, store.principle_path, store.tbd_path):
                p = get_path(uid)
                if p.exists():
                    stage_file(store.root, p)
                    break
        sha = git_commit(
            store.root, body.message,
            store.config.git.commit_name, store.config.git.commit_email,
        )
        return {"commit_sha": sha}
    except NothingToCommit as exc:
        raise conflict(str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail={"error": "git_error", "message": str(exc)})


@router.get("/git/log/{uid}")
def get_git_log(uid: str, store: Store = Depends(get_store)):
    for get_path in (store.req_path, store.principle_path, store.tbd_path):
        p = get_path(uid)
        if p.exists():
            return git_log(store.root, p)
    raise not_found(uid)
