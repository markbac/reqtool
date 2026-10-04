"""
reqtool.features.quality
========================
Advisory requirement quality rules with stable codes (FEAT-06). They never block a save.
"""

from __future__ import annotations

import re
from typing import Any

AMBIGUOUS = ("etc", "and/or", "as appropriate", "if possible", "user-friendly", "fast", "easy", "flexible",
             "robust", "adequate", "sufficient", "approximately", "as needed", "tbd", "various", "some")
EARS = re.compile(r"\b(shall|must|will)\b", re.I)
EARS_TRIGGER = re.compile(r"^\s*(when|while|if|where)\b", re.I)
MEASURABLE = re.compile(r"\d|\b(within|at least|at most|no more than|no less than|exactly)\b", re.I)

RULES = {
    "Q001": "Ambiguous wording",
    "Q002": "No acceptance criteria",
    "Q003": "Not written as a 'shall' statement",
    "Q004": "No measurable value",
    "Q005": "More than one requirement in a sentence",
    "Q006": "Title is empty or very short",
}


def check_text(title: str, description: str, criteria: int = 0) -> list[dict[str, str]]:
    """Advisory findings for a requirement as typed, before it is saved."""
    text = f"{description or ''}".strip()
    out: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        out.append({"code": code, "severity": "advisory", "rule": RULES[code], "message": message})

    if len((title or "").strip()) < 5:
        add("Q006", "Give the requirement a title of at least a few words")
    if not criteria:
        add("Q002", "Add at least one acceptance criterion so the requirement can be verified")
    if text:
        words = [w for w in AMBIGUOUS if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", text, re.I)]
        if words:
            add("Q001", "Replace vague wording: " + ", ".join(sorted(words)))
        if not EARS.search(text):
            hint = "Start with the trigger ('When ...'), then say what the system shall do" \
                if EARS_TRIGGER.match(text) else "Use 'The <system> shall <response>'"
            add("Q003", hint)
        if not MEASURABLE.search(text):
            add("Q004", "State a number, limit or condition so a test can pass or fail")
        if len(re.findall(r"\bshall\b", text, re.I)) > 1:
            add("Q005", "Split the statement: it has more than one 'shall'")
    return out


def check_requirement(req: dict[str, Any]) -> list[dict[str, str]]:
    content = req.get("content") or {}
    criteria = len(content.get("acceptance_criteria") or req.get("acceptance_criteria") or [])
    return check_text(req.get("title", ""), content.get("description", ""), criteria)
