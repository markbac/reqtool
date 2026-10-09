"""The linter: collect an item's prose, apply the rules and (optionally) Vale, and report."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from . import rules, vale
from .config import RULES, LintConfig, ValeSettings
from .text import Segment, segments

SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class LintIssue:
    uid: str
    id: str
    field: str
    line: int
    rule: str
    category: str
    message: str
    severity: str = "warning"
    suggestion: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LintReport:
    items: int = 0
    issues: list[LintIssue] = field(default_factory=list)

    def count(self, threshold: str = "info") -> int:
        limit = SEVERITY_RANK[threshold]
        return sum(1 for i in self.issues if SEVERITY_RANK.get(i.severity, 1) <= limit)

    def summary(self) -> dict[str, Any]:
        by_rule: dict[str, int] = {}
        by_severity = {"error": 0, "warning": 0, "info": 0}
        for i in self.issues:
            by_rule[i.rule] = by_rule.get(i.rule, 0) + 1
            by_severity[i.severity] = by_severity.get(i.severity, 0) + 1
        return {"items": self.items, "issues": len(self.issues), "by_rule": by_rule, "by_severity": by_severity,
                "items_with_issues": len({i.uid for i in self.issues})}


def _value(data: Mapping[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


class DocLinter:
    def __init__(self, config: LintConfig, repo_root: Optional[Path] = None) -> None:
        self.config = config
        self.repo_root = repo_root

    # -- text ---------------------------------------------------------------------------------

    def _run_rules(self, prose: list[Segment], req_type: Optional[str]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for rule, check in rules.RULE_FUNCTIONS:
            if rule in self.config.disabled_rules:
                continue
            for issue in check(prose, self.config, req_type=req_type):
                issue["severity"] = self.config.severity(rule)
                found.append(issue)
        return found

    def lint_text(self, text: str, field_name: str = "text", use_vale: bool = True) -> list[LintIssue]:
        """Lint a piece of Markdown on its own (the editor's live check)."""
        found = self._run_rules(segments(text, field_name), None)
        if use_vale and self.config.vale.enabled:
            found += self._vale_issues(text, field_name)
        return self._to_issues("", "", found)

    # -- items --------------------------------------------------------------------------------

    def _texts(self, item: Mapping[str, Any], kind: str) -> list[tuple[str, str]]:
        """(field path, text) for each piece of prose to check, in reading order."""
        out: list[tuple[str, str]] = []
        if kind == "requirement":
            for path in self.config.fields:
                val = _value(item, path)
                if isinstance(val, str) and val.strip():
                    out.append((path, val))
            for index, ac in enumerate(item.get("acceptance_criteria") or []):
                if isinstance(ac, dict) and isinstance(ac.get("text"), str) and ac["text"].strip():
                    out.append((f"acceptance_criteria[{index}]", ac["text"]))
        else:
            content = item.get("content")
            if isinstance(content, dict):
                out += [(f"content.{k}", v) for k, v in content.items() if isinstance(v, str) and v.strip()]
        return out

    def lint_item(self, item: Mapping[str, Any], kind: str = "requirement") -> list[LintIssue]:
        """Lint one requirement, principle or decision. Its fields are read as one document, so an acronym
        defined in the description counts as defined in the rationale."""
        if item.get("deleted"):
            return []
        texts = self._texts(item, kind)
        prose: list[Segment] = []
        for path, text in texts:
            prose += segments(text, path)
        found = self._run_rules(prose, item.get("req_type"))
        if self.config.vale.enabled:
            for path, text in texts:
                found += self._vale_issues(text, path)
        return self._to_issues(str(item.get("uid", "")), str(item.get("id", "")), found)

    def _vale_issues(self, text: str, field_name: str) -> list[dict[str, Any]]:
        return [{"field": field_name, "line": a["line"], "rule": f"vale:{a['rule']}", "category": "Vale",
                 "message": a["message"], "suggestion": None, "severity": a["severity"]}
                for a in vale.run(text, self.config.vale, self.repo_root)]

    @staticmethod
    def _to_issues(uid: str, item_id: str, found: Iterable[dict[str, Any]]) -> list[LintIssue]:
        issues = [LintIssue(uid, item_id, f["field"], int(f["line"]), f["rule"], f["category"], f["message"],
                            f.get("severity", "warning"), f.get("suggestion")) for f in found]
        return sorted(issues, key=lambda i: (i.field, i.line, i.rule))

    def lint_store(self, requirements: Iterable[Mapping[str, Any]], principles: Iterable[Mapping[str, Any]] = (),
                   decisions: Iterable[Mapping[str, Any]] = ()) -> LintReport:
        report = LintReport()
        for kind, items in (("requirement", requirements), ("principle", principles), ("decision", decisions)):
            for item in items:
                if item.get("deleted"):
                    continue
                report.items += 1
                report.issues += self.lint_item(item, kind)
        report.issues.sort(key=lambda i: (SEVERITY_RANK.get(i.severity, 1), i.id, i.field, i.line))
        return report


def rule_catalogue(config: LintConfig) -> list[dict[str, Any]]:
    return [{"id": rid, "description": desc, "enabled": rid not in config.disabled_rules,
             "severity": config.severity(rid)} for rid, desc in RULES.items()]


__all__ = ["DocLinter", "LintIssue", "LintReport", "ValeSettings", "rule_catalogue"]
