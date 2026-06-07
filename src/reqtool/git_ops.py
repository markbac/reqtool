"""
reqtool.git_ops
===============
Git integration. Wraps gitpython; falls back to subprocess where needed.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a git command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def is_git_repo(path: Path) -> bool:
    rc, _, _ = _run_git(["rev-parse", "--git-dir"], path)
    return rc == 0


def has_conflicts(path: Path) -> bool:
    """Return True if the working tree has unresolved merge conflicts."""
    rc, out, _ = _run_git(["status", "--porcelain"], path)
    if rc != 0:
        return False
    for line in out.splitlines():
        if line[:2] in ("UU", "AA", "DD", "AU", "UA", "DU", "UD"):
            return True
    return False


def git_status(path: Path) -> dict[str, list[str]]:
    """Return staged, unstaged, and untracked file lists."""
    rc, out, _ = _run_git(["status", "--porcelain"], path)
    staged, unstaged, untracked = [], [], []
    for line in out.splitlines():
        if len(line) < 3:
            continue
        xy = line[:2]
        fname = line[3:]
        if xy[0] in ("A", "M", "D", "R", "C") and xy[0] != " ":
            staged.append(fname)
        if xy[1] in ("M", "D"):
            unstaged.append(fname)
        if xy == "??":
            untracked.append(fname)
    return {"staged": staged, "unstaged": unstaged, "untracked": untracked}


def stage_file(repo_root: Path, file_path: Path) -> None:
    """Stage a single file."""
    rel = file_path.relative_to(repo_root)
    rc, _, err = _run_git(["add", str(rel)], repo_root)
    if rc != 0:
        raise RuntimeError(f"git add failed: {err}")


def commit(
    repo_root: Path,
    message: str,
    author_name: str = "Requirements Tool",
    author_email: str = "reqtool@example.com",
) -> str:
    """Commit staged files. Returns the commit SHA."""
    env_extras = {
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
    }
    import os
    env = {**os.environ, **env_extras}
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git commit failed: {result.stderr}")
    # Extract SHA
    rc, sha, _ = _run_git(["rev-parse", "HEAD"], repo_root)
    return sha if rc == 0 else ""


def amend_commit(repo_root: Path) -> str:
    """Amend the last commit (used for post-commit SHA writeback)."""
    result = subprocess.run(
        ["git", "commit", "--amend", "--no-edit"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git commit --amend failed: {result.stderr}")
    rc, sha, _ = _run_git(["rev-parse", "HEAD"], repo_root)
    return sha if rc == 0 else ""


def git_log(repo_root: Path, file_path: Path, max_count: int = 20) -> list[dict]:
    """Return git log entries for a specific file."""
    rel = str(file_path.relative_to(repo_root))
    rc, out, _ = _run_git(
        ["log", f"--max-count={max_count}", "--pretty=format:%H|%an|%ae|%ai|%s", "--", rel],
        repo_root,
    )
    entries = []
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split("|", 4)
            if len(parts) == 5:
                entries.append({
                    "sha": parts[0],
                    "author_name": parts[1],
                    "author_email": parts[2],
                    "date": parts[3],
                    "subject": parts[4],
                })
    return entries


def ensure_git_config(repo_root: Path, name: str, email: str) -> None:
    """Set local git user config if not already set."""
    rc, out, _ = _run_git(["config", "--local", "user.name"], repo_root)
    if rc != 0 or not out:
        _run_git(["config", "--local", "user.name", name], repo_root)
    rc, out, _ = _run_git(["config", "--local", "user.email"], repo_root)
    if rc != 0 or not out:
        _run_git(["config", "--local", "user.email", email], repo_root)


def git_create_tag(repo_root: Path, tag_name: str, message: str = "") -> str:
    """Create an annotated git tag at HEAD. Returns the SHA."""
    if message:
        rc, out, err = _run_git(["tag", "-a", tag_name, "-m", message], repo_root)
    else:
        rc, out, err = _run_git(["tag", tag_name], repo_root)
    if rc != 0:
        raise RuntimeError(f"git tag failed: {err}")
    rc2, sha, _ = _run_git(["rev-parse", tag_name + "^{}"], repo_root)
    return sha if rc2 == 0 else ""


def git_list_tags(repo_root: Path, prefix: str = "") -> list[dict]:
    """List tags, optionally filtered by prefix. Returns [{name, sha, date, message}]."""
    pattern = f"{prefix}*" if prefix else "*"
    rc, out, _ = _run_git(
        ["tag", "-l", pattern, "--format=%(refname:short)|%(objectname:short)|%(creatordate:iso)|%(subject)"],
        repo_root,
    )
    tags = []
    if rc == 0 and out:
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 3)
            if len(parts) >= 2:
                tags.append({
                    "name": parts[0],
                    "sha": parts[1],
                    "date": parts[2] if len(parts) > 2 else "",
                    "message": parts[3] if len(parts) > 3 else "",
                })
    return sorted(tags, key=lambda t: t.get("date", ""), reverse=True)


def git_diff_tree(repo_root: Path, ref_a: str, ref_b: str = "HEAD") -> list[dict]:
    """List files changed between two refs. Returns [{path, status}]."""
    rc, out, _ = _run_git(["diff", "--name-status", ref_a, ref_b], repo_root)
    changes = []
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                changes.append({"status": parts[0], "path": parts[1]})
    return changes


def git_show_file(repo_root: Path, ref: str, file_path: Path) -> Optional[str]:
    """Return file content at a specific git ref, or None if not found."""
    try:
        rel = str(file_path.relative_to(repo_root))
        rc, out, _ = _run_git(["show", f"{ref}:{rel}"], repo_root)
        return out if rc == 0 else None
    except Exception:
        return None
