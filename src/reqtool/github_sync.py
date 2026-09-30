"""
reqtool.github_sync
===================
GitHub Integration Engine.
Handles bi-directional link parsing between GitHub development repositories,
commits, pull requests, issues, and reqtool requirements.
"""

from __future__ import annotations

import re
from typing import Any
from reqtool.store import Store

# Regex pattern for requirement references in commit messages and PR titles
# e.g., "Fixes REQ-SYS-001", "Resolves #HW-002", "Ref: REQ-FW-003"
REQ_REF_PATTERN = re.compile(r'(?:fixes|resolves|refs?|closes)?\s*#?([A-Z0-9]+-(?:[A-Z0-9]+-)?\d+)', re.IGNORECASE)


def parse_requirement_refs(text: str) -> list[str]:
    """Extract requirement UIDs/IDs referenced in text."""
    if not text:
        return []
    matches = REQ_REF_PATTERN.findall(text)
    return list(set(m.upper() for m in matches))


def process_github_push_event(store: Store, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Process incoming GitHub push webhook payload and link commits to requirements."""
    results = []
    commits = payload.get("commits", [])
    repo_name = payload.get("repository", {}).get("full_name", "github")
    ref = payload.get("ref", "")

    for commit in commits:
        sha = commit.get("id", "")[:8]
        msg = commit.get("message", "")
        author = commit.get("author", {}).get("username") or commit.get("author", {}).get("name", "github")
        url = commit.get("url", f"https://github.com/{repo_name}/commit/{sha}")

        referenced_uids = parse_requirement_refs(msg)
        for req_id in referenced_uids:
            req = store.get_requirement(req_id)
            if req:
                uid = req["uid"]
                existing_links = req.get("verification", {}).get("git_commits", [])
                commit_info = f"{repo_name}@{sha}: {msg[:40]}"
                if commit_info not in existing_links:
                    existing_links.append(commit_info)
                    store.update_requirement(uid, {
                        "verification": {
                            **req.get("verification", {}),
                            "git_commits": existing_links,
                            "note": f"Linked from GitHub commit {sha} by {author}",
                        }
                    }, summary=f"Linked GitHub commit {sha}")
                    results.append({"uid": uid, "req_id": req_id, "commit_sha": sha, "repo": repo_name})
    return results
