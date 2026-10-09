"""
reqtool.github_sync
===================
GitHub Integration Engine.
Links commits to requirements without changing the requirements themselves: links live in the
sidecar file ``.reqtool/commit_links.yaml``, so a commit message never creates a requirement
version, history entry or suspect flag.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from reqtool.fileio import load_yaml, save_yaml, utcnow_iso
from reqtool.store import Store

# Anything that looks like an ID (``FR-001``, ``REQ-SYS-001``). Only candidates that match an existing
# requirement are ever used, so ``UTF-8`` or ``CVE-2024-1234`` in ordinary text link nothing.
REQ_REF_PATTERN = re.compile(r'(?<![A-Za-z0-9])#?([A-Z0-9]+-(?:[A-Z0-9]+-)?\d+)(?![A-Za-z0-9-])', re.IGNORECASE)
UID_PATTERN = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.IGNORECASE)

LINKS_FILE = "commit_links.yaml"
_write_lock = threading.Lock()


def parse_requirement_refs(text: str, known: dict[str, str] | None = None) -> list[str]:
    """Extract requirement references (upper-cased) from text.

    With ``known`` (a map of upper-cased ID or UID to requirement UID) only references that exist are returned.
    """
    if not text:
        return []
    found = {m.upper() for m in REQ_REF_PATTERN.findall(text)}
    found |= {m.upper() for m in UID_PATTERN.findall(text)}
    if known is not None:
        found &= set(known)
    return sorted(found)


def build_ref_index(store: Store) -> dict[str, str]:
    """Map upper-cased human ID and UID of every live requirement to its UID."""
    index: dict[str, str] = {}
    for uid, req in store.requirement_map().items():
        if req.get("deleted"):
            continue
        index[uid.upper()] = uid
        if req.get("id"):
            index[str(req["id"]).upper()] = uid
    return index


def _links_path(store: Store):
    return store.root / ".reqtool" / LINKS_FILE


def load_commit_links(store: Store, uid: str | None = None):
    path = _links_path(store)
    data = (load_yaml(path) if path.exists() else {}) or {}
    return data.get(uid, []) if uid is not None else data


def process_github_push_event(store: Store, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Link the commits of a push payload to the requirements they mention; returns the new links."""
    results: list[dict[str, Any]] = []
    repo_name = payload.get("repository", {}).get("full_name", "github")
    ref = payload.get("ref", "")
    index = build_ref_index(store)

    with _write_lock:
        links = load_commit_links(store)
        changed = False
        for commit in payload.get("commits", []):
            full_sha = commit.get("id", "")
            sha = full_sha[:8]
            msg = commit.get("message", "")
            author = commit.get("author", {}).get("username") or commit.get("author", {}).get("name", "github")
            url = commit.get("url") or f"https://github.com/{repo_name}/commit/{full_sha}"

            for key in parse_requirement_refs(msg, index):
                uid = index[key]
                entries = links.setdefault(uid, [])
                if any(e.get("repo") == repo_name and e.get("sha") == sha for e in entries):
                    continue
                entries.append({
                    "repo": repo_name, "sha": sha, "message": msg.splitlines()[0][:120] if msg else "",
                    "author": author, "url": url, "ref": ref, "linked_at": utcnow_iso(),
                })
                changed = True
                results.append({"uid": uid, "req_id": key, "commit_sha": sha, "repo": repo_name})
        if changed:
            save_yaml(_links_path(store), links)
    return results
