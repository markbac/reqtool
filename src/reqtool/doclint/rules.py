"""The writing rules. Each takes the prose segments of one item and returns its issues."""

from __future__ import annotations

import re
from typing import Any, Callable

from .config import RULE_ACRONYM, RULE_GLOSSARY, RULE_REDUNDANT, RULE_SHALL, RULE_VAGUE, LintConfig
from .text import Segment

Issue = dict[str, Any]  # field, line, rule, category, message, suggestion


def _bounded(pattern: str) -> str:
    return rf"(?<!\w){pattern}(?!\w)"


def _issue(segment: Segment, offset: int, rule: str, category: str, message: str, suggestion: str | None) -> Issue:
    return {"field": segment.field, "line": segment.line_at(offset), "rule": rule, "category": category,
            "message": message, "suggestion": suggestion}


def glossary(segments: list[Segment], config: LintConfig, **_: Any) -> list[Issue]:
    """Terms spelt differently from their canonical form, in any capitalisation."""
    issues: list[Issue] = []
    for canonical, variants in config.glossary.items():
        any_case = re.compile(_bounded(re.escape(canonical)), re.IGNORECASE)
        # Listed variants catch genuine misspellings such as Lw2m, which differ by more than case.
        misspellings = [v for v in variants if v.lower() != canonical.lower()]
        spelt = re.compile("|".join(_bounded(re.escape(v)) for v in misspellings)) if misspellings else None
        for segment in segments:
            for match in any_case.finditer(segment.text):
                if match.group(0) != canonical:
                    issues.append(_issue(segment, match.start(), RULE_GLOSSARY, "Glossary",
                                         f"Incorrect term capitalization '{match.group(0)}'. Preferred: '{canonical}'.",
                                         canonical))
            if spelt:
                for match in spelt.finditer(segment.text):
                    issues.append(_issue(segment, match.start(), RULE_GLOSSARY, "Glossary",
                                         f"Incorrect term '{match.group(0)}'. Preferred: '{canonical}'.", canonical))
    return issues


def redundant_phrases(segments: list[Segment], config: LintConfig, **_: Any) -> list[Issue]:
    """Wordy phrases, matched across soft line wraps."""
    issues: list[Issue] = []
    for phrase, replacement in config.redundant_phrases.items():
        words = (re.escape(word) for word in phrase.split())
        pattern = re.compile(_bounded(r"\s+".join(words)), re.IGNORECASE)
        for segment in segments:
            for match in pattern.finditer(segment.text):
                issues.append(_issue(segment, match.start(), RULE_REDUNDANT, "Style",
                                     f"Redundant phrase found: '{phrase}'. Consider simplifying.",
                                     replacement or "remove it"))
    return issues


def vague_terms(segments: list[Segment], config: LintConfig, **_: Any) -> list[Issue]:
    """Words that cannot be verified: a requirement using them has no clear pass or fail."""
    issues: list[Issue] = []
    for term in config.vague_terms:
        words = (re.escape(word) for word in term.split())
        pattern = re.compile(_bounded(r"\s+".join(words)), re.IGNORECASE)
        for segment in segments:
            for match in pattern.finditer(segment.text):
                issues.append(_issue(segment, match.start(), RULE_VAGUE, "Clarity",
                                     f"Vague term '{match.group(0)}' cannot be verified.",
                                     "State a measurable value or condition."))
    return issues


def shall_statement(segments: list[Segment], config: LintConfig, *, req_type: str | None = None,
                    **_: Any) -> list[Issue]:
    """The description of a requirement should contain 'shall' (only for the types listed in the settings)."""
    if config.statement_types and req_type not in config.statement_types:
        return []
    described = [s for s in segments if s.field == "content.description"]
    if not described or any(re.search(_bounded("shall"), s.text, re.IGNORECASE) for s in described):
        return []
    return [_issue(described[0], 0, RULE_SHALL, "Statement",
                   "The description does not contain 'shall'.", "Write it as 'The system shall ...'.")]


# --- acronyms -----------------------------------------------------------------------------------

_STOP_WORDS = {"of", "as", "a", "an", "the", "to", "and", "for", "in", "on", "by", "with"}
_WORD = re.compile(r"[A-Za-z0-9]+")
_FORWARD = re.compile(r"\(\s*([A-Za-z0-9]{2,})\s*\)")  # Full Name (ABC)
_REVERSE = re.compile(r"(?<![\w])([A-Za-z0-9]{2,})\s*\(([^()]+)\)")  # ABC (Full Name)
_USE = re.compile(r"(?<![A-Za-z0-9_])[A-Z][A-Z0-9]+(?![A-Za-z0-9_])")


def _looks_like_acronym(token: str) -> bool:
    return sum(ch.isupper() for ch in token) >= 2


def _expands(words: list[str], acronym: str) -> bool:
    """Whether ``words`` could spell out ``acronym``: the first word starts it and the rest follow in order."""
    if len(words) < 2 or words[0].lower() in _STOP_WORDS:
        return False
    letters = iter(acronym.lower())
    if words[0][0].lower() != acronym[0].lower():
        return False
    return all(any(letter == word[0].lower() for letter in letters) for word in words if word.lower() not in _STOP_WORDS)


def _definitions(text: str) -> list[tuple[str, int]]:
    """Acronym definitions in ``text`` as (acronym, offset of the acronym), in either order."""
    found: list[tuple[str, int]] = []
    for match in _FORWARD.finditer(text):
        acronym = match.group(1)
        if not _looks_like_acronym(acronym):
            continue
        words = _WORD.findall(text[: match.start()])
        for count in range(min(len(words), len(acronym) + 2), 1, -1):
            if _expands(words[-count:], acronym):
                found.append((acronym, match.start(1)))
                break
    for match in _REVERSE.finditer(text):
        acronym = match.group(1)
        if _looks_like_acronym(acronym) and _expands(_WORD.findall(match.group(2)), acronym):
            found.append((acronym, match.start(1)))
    return found


def acronyms(segments: list[Segment], config: LintConfig, **_: Any) -> list[Issue]:
    """The first use of each all-capitals acronym that is not defined, or is defined only later."""
    first_definition: dict[str, tuple[int, int, int]] = {}  # acronym -> (segment, offset, line)
    defining: set[tuple[int, int]] = set()
    for index, segment in enumerate(segments):
        for acronym, offset in _definitions(segment.text):
            defining.add((index, offset))
            first_definition.setdefault(acronym, (index, offset, segment.line_at(offset)))

    exempt = config.allowed_acronyms | set(config.glossary)
    reported: set[str] = set()
    issues: list[Issue] = []
    for index, segment in enumerate(segments):
        for match in _USE.finditer(segment.text):
            token = match.group(0)
            if len(token) < config.acronym_min_length or not _looks_like_acronym(token):
                continue
            if token in exempt or token in reported or (index, match.start()) in defining:
                continue
            defined = first_definition.get(token)
            if defined and (defined[0], defined[1]) < (index, match.start()):
                continue
            reported.add(token)
            message = (f"Acronym '{token}' is used before it is defined on line {defined[2]}." if defined
                       else f"Acronym '{token}' is used without being defined.")
            issues.append(_issue(segment, match.start(), RULE_ACRONYM, "Acronym", message,
                                 f"Define it on first use, for example 'Full Name ({token})'."))
    return issues


RULE_FUNCTIONS: tuple[tuple[str, Callable[..., list[Issue]]], ...] = (
    (RULE_GLOSSARY, glossary),
    (RULE_REDUNDANT, redundant_phrases),
    (RULE_ACRONYM, acronyms),
    (RULE_VAGUE, vague_terms),
    (RULE_SHALL, shall_statement),
)
