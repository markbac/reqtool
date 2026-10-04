"""Validation and git calls for fetching modules from a remote repository."""

from __future__ import annotations

import re
from pathlib import Path

_REMOTE_SCHEMES = ("http", "https", "ssh", "git")
_SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[A-Za-z0-9._~/-]+$")
_REMOTE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


def _validate_remote_url(url: str) -> None:
    """Allow only plain http(s)/ssh/git URLs or scp-style ``user@host:path``.

    Rejects option-like values (leading ``-``, e.g. ``--upload-pack=...``),
    whitespace/control characters, ``ext::``/``file:`` transports and local paths.
    """
    from urllib.parse import urlparse

    if not url or url.startswith("-") or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("Unsupported git remote")
    if _SCP_LIKE_RE.match(url):
        return
    parsed = urlparse(url)
    if parsed.scheme not in _REMOTE_SCHEMES or not parsed.hostname:
        raise ValueError(f"Unsupported git remote URI scheme for '{url}'")


def _validate_remote_ref(ref: str) -> None:
    if not _REMOTE_REF_RE.match(ref) or ".." in ref:
        raise ValueError(f"Invalid git_ref '{ref}'")


def _git_remote(args: list[str], cwd: Path) -> None:
    """Run git for a network operation: restricted transports, no prompts, timeout."""
    import os
    import subprocess

    cmd = [
        "git",
        "-c", "protocol.allow=never",
        "-c", "protocol.https.allow=always",
        "-c", "protocol.http.allow=always",
        "-c", "protocol.ssh.allow=always",
        "-c", "protocol.git.allow=always",
        *args,
    ]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env, timeout=180)
    except subprocess.TimeoutExpired:
        raise ValueError(f"git {args[0]} timed out")
    if res.returncode != 0:
        raise ValueError(f"git {args[0]} failed: {(res.stderr or res.stdout).strip()[:500]}")
