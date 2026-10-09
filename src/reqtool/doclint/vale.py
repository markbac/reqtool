"""Run Vale (https://vale.sh) on text, with its configuration generated from the repository's lint settings."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .. import tooling
from .config import ValeSettings

log = logging.getLogger(__name__)

BUNDLED_STYLES = Path(__file__).parent.parent / "defaults" / "styles"
_SEVERITY = {"error": "error", "warning": "warning", "suggestion": "info"}


def find_binary(settings: ValeSettings) -> Optional[str]:
    """The configured command on PATH, or the copy ``req tools`` installed."""
    return tooling.find_vale(settings.binary or "vale")


def status(settings: ValeSettings, repo_root: Optional[Path] = None) -> dict[str, Any]:
    """Whether Vale can run with these settings, for the settings editor to show."""
    binary = find_binary(settings)
    out: dict[str, Any] = {"enabled": settings.enabled, "binary": binary, "available": bool(binary),
                           "styles_path": str(styles_path(settings, repo_root)), "styles_found": [], "version": None}
    sp = styles_path(settings, repo_root)
    if sp.is_dir():
        out["styles_found"] = sorted(p.name for p in sp.iterdir() if p.is_dir())
    if binary:
        try:
            res = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5)
            out["version"] = (res.stdout or res.stderr).strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
    return out


def styles_path(settings: ValeSettings, repo_root: Optional[Path]) -> Path:
    if settings.styles_path:
        path = Path(settings.styles_path)
        return path if path.is_absolute() or repo_root is None else repo_root / path
    return BUNDLED_STYLES


def build_ini(settings: ValeSettings, repo_root: Optional[Path]) -> str:
    """The .vale.ini text for these settings."""
    lines = [f"StylesPath = {styles_path(settings, repo_root)}",
             f"MinAlertLevel = {settings.min_alert_level}", "", "[*]",
             f"BasedOnStyles = {', '.join(settings.styles)}"]
    lines += [f"{check} = NO" for check in settings.disabled_checks]
    return "\n".join(lines) + "\n"


def run(text: str, settings: ValeSettings, repo_root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Alerts from Vale as dicts (line, rule, message, severity). Returns [] when Vale is missing, slow or fails."""
    if not text or not text.strip():
        return []
    binary = find_binary(settings)
    if not binary:
        return []
    with tempfile.TemporaryDirectory(prefix="reqtool-vale-") as tmp:
        source = Path(tmp) / "text.md"
        source.write_text(text, encoding="utf-8")
        if settings.config_file:
            config = Path(settings.config_file)
            config = config if config.is_absolute() or repo_root is None else repo_root / config
            if not config.exists():
                log.warning("Vale config file %s does not exist; skipping the Vale check", config)
                return []
        else:
            config = Path(tmp) / ".vale.ini"
            config.write_text(build_ini(settings, repo_root), encoding="utf-8")
        cmd = [binary, "--output=JSON", f"--config={config}", str(source)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=settings.timeout_seconds)
        except subprocess.TimeoutExpired:
            log.warning("Vale did not finish within %ss; skipping the prose check", settings.timeout_seconds)
            return []
        except OSError as exc:
            log.warning("Vale could not be started: %s", exc)
            return []
        if not res.stdout or not res.stdout.strip():
            return []
        try:
            data = json.loads(res.stdout)
        except ValueError:
            return []
    alerts: list[dict[str, Any]] = []
    for alert_list in data.values():
        if not isinstance(alert_list, list):
            continue
        for alert in alert_list:
            severity = str(alert.get("Severity", "warning")).lower()
            alerts.append({"line": alert.get("Line", 1), "rule": alert.get("Check", "vale.rule"),
                           "message": alert.get("Message", ""), "severity": _SEVERITY.get(severity, "warning")})
    return alerts
