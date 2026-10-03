"""
reqtool.git_ops
===============
Git integration. Wraps the git CLI via subprocess.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/~^@{}+-]{0,199}$")


class InvalidRef(ValueError):
    """A user-supplied git ref / tag name failed validation."""


def validate_ref(ref: str) -> str:
    """Return ``ref`` if it is a safe git revision or tag name, else raise InvalidRef.

    Rejects anything starting with ``-`` (option injection, e.g. ``--output=...``),
    ranges (``..``), whitespace/control characters and over-long values.
    """
    if not isinstance(ref, str) or not _REF_RE.match(ref) or ".." in ref or ref.endswith(".lock"):
        raise InvalidRef(f"Invalid git ref: {ref!r}")
    return ref


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


def dirty_paths(path: Path, prefixes: tuple[str, ...]) -> list[str]:
    """Paths with uncommitted changes (staged, unstaged or untracked) under any of ``prefixes``."""
    rc, out, _ = _run_git(["status", "--porcelain", "-uall", "--", *prefixes], path)
    if rc != 0:
        return []
    return [line[3:].split(" -> ")[-1].strip().strip('"') for line in out.splitlines() if line.strip()]


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


class NothingToCommit(RuntimeError):
    """Raised by commit() when there is nothing staged."""


def commit(
    repo_root: Path,
    message: str,
    author_name: str = "Requirements Tool",
    author_email: str = "reqtool@example.com",
    paths: Optional[list[Path]] = None,
) -> str:
    """Commit staged files and return the commit SHA.

    With ``paths``, only those files are committed (``git commit --only``);
    anything else that happens to be staged is left staged and uncommitted.
    """
    env_extras = {
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
    }
    import os
    env = {**os.environ, **env_extras}
    result = subprocess.run(
        ["git", "commit", "-m", message]
        + (["--only", "--", *[str(Path(p).relative_to(repo_root)) for p in paths]] if paths else []),
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if "nothing to commit" in detail or "no changes added to commit" in detail:
            raise NothingToCommit("Nothing staged to commit")
        raise RuntimeError(f"git commit failed: {detail}")
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
    validate_ref(tag_name)
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
    validate_ref(ref_a)
    validate_ref(ref_b)
    rc, out, _ = _run_git(["diff", "--name-status", ref_a, ref_b, "--"], repo_root)
    changes = []
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                changes.append({"status": parts[0], "path": parts[1]})
    return changes


def git_show_file(repo_root: Path, ref: str, file_path: Path) -> Optional[str]:
    """Return file content at a specific git ref, or None if not found."""
    validate_ref(ref)
    try:
        rel = str(file_path.relative_to(repo_root))
        rc, out, _ = _run_git(["show", f"{ref}:{rel}"], repo_root)
        return out if rc == 0 else None
    except Exception:
        return None
