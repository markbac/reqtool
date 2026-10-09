"""Writing checks: read and save the repository's lint settings, and lint text, one item or everything."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from reqtool.doclint import DocLinter, parse_settings, settings_problems
from reqtool.doclint import vale as vale_runner
from reqtool.doclint.config import default_settings, merged_settings
from reqtool.doclint.linter import LintReport, rule_catalogue
from reqtool.store import Store
from .errors import Invalid, NotFound

SETTINGS_FILE = "lint.yaml"


class LintService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.path = store.root / ".reqtool" / SETTINGS_FILE

    # -- settings ----------------------------------------------------------------------------

    def raw_settings(self) -> dict[str, Any]:
        """The settings as stored, laid over the defaults so every setting is present."""
        data: Optional[Mapping[str, Any]] = None
        if self.store.storage.exists(self.path):
            loaded = self.store.storage.read(self.path)
            data = loaded if isinstance(loaded, dict) else None
        return merged_settings(data)

    def linter(self) -> DocLinter:
        try:
            config = parse_settings(self.raw_settings())
        except ValueError:  # a hand-edited file with a mistake: fall back so the rest of the tool keeps working
            config = parse_settings(default_settings())
        return DocLinter(config, self.store.root)

    def describe(self) -> dict[str, Any]:
        raw = self.raw_settings()
        problems = settings_problems(raw)
        config = parse_settings(raw if not problems else default_settings())
        return {
            "settings": raw,
            "file": f".reqtool/{SETTINGS_FILE}",
            "exists": self.store.storage.exists(self.path),
            "problems": problems,
            "rules": rule_catalogue(config),
            "vale": vale_runner.status(config.vale, self.store.root),
            "defaults": default_settings(),
        }

    def save(self, data: Mapping[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(data) - set(default_settings()))
        if unknown:
            raise Invalid(f"Unknown setting(s): {', '.join(unknown)}", errors=[f"Unknown setting '{k}'" for k in unknown])
        full = merged_settings(data)
        problems = settings_problems(full)
        if problems:
            raise Invalid("; ".join(problems), errors=problems)
        self.store.storage.write(self.path, full)
        return self.describe()

    # -- linting -----------------------------------------------------------------------------

    def lint_text(self, text: str) -> dict[str, Any]:
        linter = self.linter()
        if not linter.config.enabled:
            return {"enabled": False, "issues": []}
        return {"enabled": True, "issues": [i.as_dict() for i in linter.lint_text(text)]}

    def lint_requirement(self, uid: str) -> dict[str, Any]:
        req = self.store.get_requirement(uid)
        if req is None:
            raise NotFound(uid)
        linter = self.linter()
        if not linter.config.enabled:
            return {"enabled": False, "uid": uid, "issues": []}
        return {"enabled": True, "uid": uid, "issues": [i.as_dict() for i in linter.lint_item(req)]}

    def report(self) -> tuple[DocLinter, LintReport]:
        linter = self.linter()
        if not linter.config.enabled:
            return linter, LintReport()
        return linter, linter.lint_store(self.store.live_requirements(), self.store.live_principles(),
                                         self.store.live_decisions())

    def lint_all(self, severity: str = "info", limit: int = 500) -> dict[str, Any]:
        linter, report = self.report()
        from reqtool.doclint.linter import SEVERITY_RANK
        keep = [i for i in report.issues if SEVERITY_RANK.get(i.severity, 1) <= SEVERITY_RANK.get(severity, 2)]
        return {"enabled": linter.config.enabled, "summary": report.summary(), "truncated": len(keep) > limit,
                "issues": [i.as_dict() for i in keep[:limit]]}

    def validation_findings(self) -> list[dict[str, str]]:
        """Findings as validation messages, when the settings ask for them to be part of ``req validate``."""
        linter = self.linter()
        config = linter.config
        if not config.enabled or not config.include_in_validation:
            return []
        if not config.vale.include_in_validation:
            config.vale.enabled = False
        report = linter.lint_store(self.store.live_requirements(), self.store.live_principles(),
                                   self.store.live_decisions())
        return [{"code": i.rule, "severity": i.severity, "uid": i.uid, "field": i.field,
                 "message": f"[{i.id} {i.field} line {i.line}] {i.message}"} for i in report.issues]
