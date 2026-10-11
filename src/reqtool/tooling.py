"""Find, check and install the external tools reqtool can use.

Python and git are required and only checked. Vale (https://vale.sh) is optional: it is downloaded from its
GitHub release, checked against the release's published SHA-256 sums, and kept in ``~/.reqtool/tools`` (or
``$REQTOOL_TOOLS_DIR``) so no administrator rights are needed. Node.js is only needed to build the web UI from
source, so it is reported but never installed.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

RELEASES = "https://github.com/vale-cli/vale/releases"
FALLBACK_VALE_VERSION = "3.24.0"  # used only when the latest release cannot be looked up (newest release checked to install and verify)
RETRY_AFTER_SECONDS = 24 * 3600  # after a failed download, setup scripts wait this long before trying again
TIMEOUT = 20


class ToolError(Exception):
    """A tool could not be installed. The message says why and what to do instead."""


@dataclass
class ToolStatus:
    name: str
    ok: bool
    required: bool
    detail: str
    path: Optional[str] = None


def tools_dir() -> Path:
    override = os.environ.get("REQTOOL_TOOLS_DIR")
    return Path(override) if override else Path.home() / ".reqtool" / "tools"


def _exe(name: str) -> str:
    return name + ".exe" if sys.platform == "win32" else name


def installed_vale() -> Optional[Path]:
    path = tools_dir() / _exe("vale")
    return path if path.is_file() else None


def find_vale(command: str = "vale") -> Optional[str]:
    """The Vale to run: the configured command if it is on PATH or a file, else the copy reqtool installed."""
    found = shutil.which(command)
    if found:
        return found
    if command in ("vale", _exe("vale")):
        ours = installed_vale()
        return str(ours) if ours else None
    return None


def vale_version(binary: str) -> Optional[str]:
    try:
        res = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return (res.stdout or res.stderr).strip() or None


# -- download -----------------------------------------------------------------------------------

def asset_name(version: str, system: Optional[str] = None, machine: Optional[str] = None) -> str:
    """The release file for this machine, named as Vale's GoReleaser config names them."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    os_name = {"linux": "Linux", "darwin": "macOS", "windows": "Windows"}.get(system)
    if os_name is None:
        raise ToolError(f"No Vale download for {system}. Install it from https://vale.sh/docs/install")
    arch = "arm64" if machine in ("arm64", "aarch64") else "64-bit" if machine in ("x86_64", "amd64") else None
    if arch is None:
        raise ToolError(f"No Vale download for {machine}. Install it from https://vale.sh/docs/install")
    ext = "zip" if os_name == "Windows" else "tar.gz"
    return f"vale_{version}_{os_name}_{arch}.{ext}"


def _fetch(url: str, opener: Callable = urllib.request.urlopen) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "reqtool"})
    try:
        with opener(request, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise ToolError(f"Could not download {url}: {exc}") from exc


def latest_vale_version(opener: Callable = urllib.request.urlopen) -> str:
    """The newest release number, read from the redirect of /releases/latest (no API quota used)."""
    request = urllib.request.Request(f"{RELEASES}/latest", method="HEAD", headers={"User-Agent": "reqtool"})
    try:
        with opener(request, timeout=TIMEOUT) as response:
            tag = response.geturl().rstrip("/").rsplit("/", 1)[-1]
    except (urllib.error.URLError, OSError):
        return FALLBACK_VALE_VERSION
    return tag[1:] if tag.startswith("v") and tag[1:2].isdigit() else FALLBACK_VALE_VERSION


def _expected_sum(checksums: str, name: str) -> str:
    for line in checksums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    raise ToolError(f"{name} is not in the release's checksum list, so it was not installed")


def _extract(blob: bytes, name: str, dest: Path) -> None:
    """Write only the Vale program from the archive (never other members, so a bad path cannot escape)."""
    target = _exe("vale")
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            member = next((m for m in archive.namelist() if Path(m).name == target), None)
            data = archive.read(member) if member else None
    else:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
            entry = next((m for m in archive.getmembers() if m.isfile() and Path(m.name).name == target), None)
            handle = archive.extractfile(entry) if entry else None
            data = handle.read() if handle else None
    if data is None:
        raise ToolError(f"{name} does not contain {target}")
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / target
    tmp = out.with_suffix(out.suffix + ".part")
    tmp.write_bytes(data)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    tmp.replace(out)


def install_vale(version: Optional[str] = None, opener: Callable = urllib.request.urlopen,
                 dest: Optional[Path] = None) -> Path:
    """Download Vale, verify it and put it in the tools folder. Returns the program's path."""
    version = (version or os.environ.get("REQTOOL_VALE_VERSION") or latest_vale_version(opener)).lstrip("v")
    name = asset_name(version)
    base = f"{RELEASES}/download/v{version}"
    checksums = _fetch(f"{base}/vale_{version}_checksums.txt", opener).decode("utf-8", "replace")
    blob = _fetch(f"{base}/{name}", opener)
    if hashlib.sha256(blob).hexdigest() != _expected_sum(checksums, name):
        raise ToolError(f"The downloaded {name} does not match its published checksum, so it was not installed")
    folder = dest or tools_dir()
    _extract(blob, name, folder)
    return folder / _exe("vale")


# -- check and install --------------------------------------------------------------------------

def _failure_marker() -> Path:
    return tools_dir() / ".vale-install-failed"


def recently_failed() -> bool:
    marker = _failure_marker()
    return marker.is_file() and time.time() - marker.stat().st_mtime < RETRY_AFTER_SECONDS


def check_tools() -> list[ToolStatus]:
    """What is available now. Nothing is installed."""
    out: list[ToolStatus] = []
    ok = sys.version_info >= (3, 11)
    out.append(ToolStatus("python", ok, True, platform.python_version() + ("" if ok else " (3.11 or newer is needed)"),
                          sys.executable))
    git = shutil.which("git")
    out.append(ToolStatus("git", bool(git), True, "found" if git else "not found: install it from https://git-scm.com/", git))
    node = shutil.which("npm")
    out.append(ToolStatus("node", bool(node), False,
                          "found" if node else "not found (only needed to build the web UI from source: https://nodejs.org/)", node))
    vale = find_vale()
    version = vale_version(vale) if vale else None
    out.append(ToolStatus("vale", bool(vale), False,
                          (version or "found") if vale else "not installed (optional prose linter: run `req tools`)", vale))
    return out


def ensure_tools(install: bool = True, vale_version_wanted: Optional[str] = None, force: bool = False,
                 opener: Callable = urllib.request.urlopen) -> list[ToolStatus]:
    """Check everything, and install Vale when it is missing. A failed install is reported, never raised."""
    statuses = check_tools()
    vale = next(s for s in statuses if s.name == "vale")
    if vale.ok or not install:
        return statuses
    if recently_failed() and not force:
        vale.detail = "not installed (the last download failed: run `req tools --force` to try again)"
        return statuses
    try:
        path = install_vale(vale_version_wanted, opener)
    except ToolError as exc:
        vale.detail = f"not installed: {exc}"
        try:
            _failure_marker().parent.mkdir(parents=True, exist_ok=True)
            _failure_marker().touch()
        except OSError:
            pass
        return statuses
    _failure_marker().unlink(missing_ok=True)
    vale.ok, vale.path = True, str(path)
    vale.detail = (vale_version(str(path)) or "installed") + f" (installed in {path.parent})"
    return statuses
