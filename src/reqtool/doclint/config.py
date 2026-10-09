"""Lint settings: the defaults, how they are read from ``.reqtool/lint.yaml``, and how they are checked."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

RULE_GLOSSARY = "DOC001"
RULE_REDUNDANT = "DOC002"
RULE_ACRONYM = "DOC003"
RULE_VAGUE = "REQ001"
RULE_SHALL = "REQ002"

RULES: dict[str, str] = {
    RULE_GLOSSARY: "A term is not written the way the glossary spells it",
    RULE_REDUNDANT: "A wordy phrase has a shorter form",
    RULE_ACRONYM: "An acronym is used before it is defined",
    RULE_VAGUE: "A vague or unmeasurable term makes the text hard to verify",
    RULE_SHALL: "A requirement statement does not say 'shall'",
}
SEVERITIES = ("error", "warning", "info")
VALE_LEVELS = ("suggestion", "warning", "error")

DEFAULT_SETTINGS: dict[str, Any] = {
    "schema_version": "1.0.0",
    # Master switch for the writing check (the editor panel, `req lint` and the API).
    "enabled": True,
    # Also report findings in `req validate` and POST /validate. Off by default so existing checks are unchanged.
    "include_in_validation": False,
    # Which item text is checked. A requirement's acceptance criteria are always included.
    "fields": ["content.description", "content.rationale", "content.extended_description"],
    # Item types REQ002 applies to (empty: all types). REQ002 is off until enabled below.
    "statement_types": [],
    "disabled_rules": [RULE_SHALL],
    "severities": {RULE_GLOSSARY: "warning", RULE_REDUNDANT: "warning", RULE_ACRONYM: "info",
                   RULE_VAGUE: "warning", RULE_SHALL: "info"},
    # Canonical spelling -> spellings that are wrong. Any capitalisation of the canonical form is also flagged.
    "glossary": {
        "LwM2M": ["lwm2m", "LWM2M", "Lw2m"], "DTLS": ["dtls", "Dtls"], "UART": ["uart", "Uart"],
        "MQTT": ["mqtt", "Mqtt"], "IPv6": ["ipv6", "Ipv6"], "API": ["api", "Api"], "JSON": ["json", "Json"],
        "YAML": ["yaml", "Yaml"], "HTTP": ["http", "Http"], "HTTPS": ["https", "Https"],
    },
    # Wordy phrase -> the shorter wording (empty string: just remove it).
    "redundant_phrases": {
        "in order to": "to", "at this point in time": "now", "due to the fact that": "because",
        "for the purpose of": "for", "has the ability to": "can", "it is important to note that": "",
    },
    "vague_terms": [
        "etc", "and/or", "as appropriate", "as required", "if possible", "user-friendly", "easy to use",
        "fast", "robust", "adequate", "sufficient", "flexible", "state-of-the-art", "minimal", "reasonable",
    ],
    "acronym_min_length": 3,
    # All-capitals words common enough not to need a definition.
    "allowed_acronyms": ["TOC", "URL", "CLI", "HTML", "CSS", "SVG", "PNG", "CPU", "RAM", "ROM", "OK", "NOTE",
                         "TODO", "FIXME", "WARNING", "IMPORTANT", "TIP", "README", "LICENSE", "FAQ", "PDF", "USB",
                         "TBD", "SHALL", "UID", "ID"],
    # Vale (https://vale.sh) is an optional prose linter. reqtool writes its configuration from these settings
    # unless `config_file` names your own .vale.ini.
    "vale": {
        "enabled": False,
        "binary": "vale",
        "config_file": None,
        "styles_path": None,
        "styles": ["INCOSE"],
        "disabled_checks": [],
        "min_alert_level": "warning",
        "timeout_seconds": 10,
        "include_in_validation": False,
    },
}


def default_settings() -> dict[str, Any]:
    """A fresh copy of every setting, as written to a new repository's ``.reqtool/lint.yaml``."""
    return copy.deepcopy(DEFAULT_SETTINGS)


@dataclass
class ValeSettings:
    enabled: bool = False
    binary: str = "vale"
    config_file: str | None = None
    styles_path: str | None = None
    styles: list[str] = field(default_factory=lambda: ["INCOSE"])
    disabled_checks: list[str] = field(default_factory=list)
    min_alert_level: str = "warning"
    timeout_seconds: float = 10
    include_in_validation: bool = False


@dataclass
class LintConfig:
    enabled: bool = True
    include_in_validation: bool = False
    fields: list[str] = field(default_factory=list)
    statement_types: list[str] = field(default_factory=list)
    disabled_rules: set[str] = field(default_factory=set)
    severities: dict[str, str] = field(default_factory=dict)
    glossary: dict[str, list[str]] = field(default_factory=dict)
    redundant_phrases: dict[str, str] = field(default_factory=dict)
    vague_terms: list[str] = field(default_factory=list)
    acronym_min_length: int = 3
    allowed_acronyms: set[str] = field(default_factory=set)
    vale: ValeSettings = field(default_factory=ValeSettings)

    def severity(self, rule: str) -> str:
        return self.severities.get(rule, "warning")


_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def settings_problems(data: Mapping[str, Any]) -> list[str]:
    """Everything wrong with a settings document (an empty list means it can be saved)."""
    problems: list[str] = []

    def kind(key: str, types: tuple[type, ...], label: str) -> bool:
        if key in data and not isinstance(data[key], types):
            problems.append(f"'{key}' must be {label}")
            return False
        return True

    kind("enabled", (bool,), "true or false")
    kind("include_in_validation", (bool,), "true or false")
    if kind("fields", (list,), "a list of field paths"):
        for f in data.get("fields") or []:
            if not isinstance(f, str) or not _FIELD.match(f):
                problems.append(f"'{f}' is not a field path such as content.description")
    kind("statement_types", (list,), "a list of item types")
    if kind("disabled_rules", (list,), "a list of rule ids"):
        for r in data.get("disabled_rules") or []:
            if r not in RULES:
                problems.append(f"Unknown rule '{r}' in disabled_rules (rules: {', '.join(RULES)})")
    if kind("severities", (dict,), "a map of rule id to severity"):
        for rule, sev in (data.get("severities") or {}).items():
            if rule not in RULES:
                problems.append(f"Unknown rule '{rule}' in severities")
            if sev not in SEVERITIES:
                problems.append(f"Severity '{sev}' for {rule} must be one of {', '.join(SEVERITIES)}")
    if kind("glossary", (dict,), "a map of term to wrong spellings"):
        for term, wrong in (data.get("glossary") or {}).items():
            if not isinstance(term, str) or not term.strip():
                problems.append("A glossary term cannot be empty")
            if not isinstance(wrong, list) or not all(isinstance(w, str) for w in wrong):
                problems.append(f"Glossary entry '{term}' must be a list of wrong spellings")
    if kind("redundant_phrases", (dict,), "a map of phrase to replacement"):
        for phrase, repl in (data.get("redundant_phrases") or {}).items():
            if not str(phrase).strip():
                problems.append("A wordy phrase cannot be empty")
            if not isinstance(repl, str):
                problems.append(f"The replacement for '{phrase}' must be text (empty to just remove it)")
    if kind("vague_terms", (list,), "a list of terms"):
        if not all(isinstance(t, str) and t.strip() for t in data.get("vague_terms") or []):
            problems.append("Every vague term must be non-empty text")
    if "acronym_min_length" in data and (not isinstance(data["acronym_min_length"], int)
                                         or isinstance(data["acronym_min_length"], bool)
                                         or not 2 <= data["acronym_min_length"] <= 10):
        problems.append("'acronym_min_length' must be a whole number from 2 to 10")
    kind("allowed_acronyms", (list,), "a list of acronyms")
    vale = data.get("vale")
    if vale is not None:
        if not isinstance(vale, dict):
            problems.append("'vale' must be a map of settings")
        else:
            for key in ("enabled", "include_in_validation"):
                if key in vale and not isinstance(vale[key], bool):
                    problems.append(f"vale.{key} must be true or false")
            if vale.get("min_alert_level", "warning") not in VALE_LEVELS:
                problems.append(f"vale.min_alert_level must be one of {', '.join(VALE_LEVELS)}")
            timeout = vale.get("timeout_seconds", 10)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 120:
                problems.append("vale.timeout_seconds must be a number from 1 to 120")
            for key in ("styles", "disabled_checks"):
                if key in vale and (not isinstance(vale[key], list) or not all(isinstance(s, str) for s in vale[key])):
                    problems.append(f"vale.{key} must be a list of names")
            for key in ("binary", "config_file", "styles_path"):
                if vale.get(key) is not None and not isinstance(vale[key], str):
                    problems.append(f"vale.{key} must be text or empty")
            for name in vale.get("styles") or []:
                if isinstance(name, str) and not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                    problems.append(f"Vale style '{name}' may only use letters, digits, '.', '_' and '-'")
    return problems


def merged_settings(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """``data`` laid over the defaults, so a file written by an older version still has every setting."""
    out = default_settings()
    for key, value in (data or {}).items():
        if key in ("vale", "severities") and isinstance(value, dict):
            out[key].update(value)
        else:
            out[key] = value
    return out


def parse_settings(data: Mapping[str, Any] | None) -> LintConfig:
    full = merged_settings(data)
    problems = settings_problems(full)
    if problems:
        raise ValueError("; ".join(problems))
    v = full["vale"]
    return LintConfig(
        enabled=bool(full["enabled"]),
        include_in_validation=bool(full["include_in_validation"]),
        fields=list(full["fields"]),
        statement_types=list(full["statement_types"]),
        disabled_rules=set(full["disabled_rules"]),
        severities=dict(full["severities"]),
        glossary={k: list(w) for k, w in full["glossary"].items()},
        redundant_phrases=dict(full["redundant_phrases"]),
        vague_terms=list(full["vague_terms"]),
        acronym_min_length=int(full["acronym_min_length"]),
        allowed_acronyms=set(full["allowed_acronyms"]),
        vale=ValeSettings(
            enabled=bool(v["enabled"]), binary=str(v.get("binary") or "vale"), config_file=v.get("config_file") or None,
            styles_path=v.get("styles_path") or None, styles=list(v["styles"]), disabled_checks=list(v["disabled_checks"]),
            min_alert_level=str(v["min_alert_level"]), timeout_seconds=float(v["timeout_seconds"]),
            include_in_validation=bool(v["include_in_validation"])),
    )
