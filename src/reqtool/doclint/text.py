"""Turn Markdown text into the prose the rules should look at.

Fenced code, inline code, HTML, link destinations, URLs, e-mail addresses and file names never reach the
rules: they are replaced with spaces (or a marker) so offsets and line numbers stay right.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass

_FENCE = re.compile(r"^\s*(```|~~~)")
_URL = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_NAME = re.compile(r"(?<![\w])[\w-]+(?:[./\\][\w-]+)+")  # config.json, docs/api: identifiers, not prose
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_HTML = re.compile(r"</?[A-Za-z][^>\n]*>")
_LINK_TARGET = re.compile(r"(\]\()[^)\n]*(\))")
_MARKUP = re.compile(r"^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)")
_GAP = "￼"  # stands in for inline code and HTML, which are not prose and must not join words


@dataclass
class Segment:
    """One paragraph of prose with the source line of each part, for one field of an item."""

    text: str
    starts: list[int]
    lines: list[int]
    field: str = ""

    def line_at(self, offset: int) -> int:
        return self.lines[max(bisect_right(self.starts, offset) - 1, 0)]


def _blank(match: re.Match[str]) -> str:
    return " " * len(match.group(0))


def _clean_line(line: str) -> str:
    line = _INLINE_CODE.sub(lambda m: _GAP * len(m.group(0)), line)
    line = _HTML.sub(lambda m: _GAP * len(m.group(0)), line)
    line = _LINK_TARGET.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - 2) + m.group(2), line)
    for pattern in (_URL, _EMAIL, _NAME):
        line = pattern.sub(_blank, line)
    return _MARKUP.sub(lambda m: " " * len(m.group(0)), line)


def segments(text: str, field_name: str = "") -> list[Segment]:
    """The prose paragraphs of ``text``. Line numbers count from 1 within ``text``."""
    found: list[Segment] = []
    parts: list[str] = []
    starts: list[int] = []
    lines: list[int] = []
    length = 0

    def flush() -> None:
        nonlocal parts, starts, lines, length
        if parts and "".join(parts).strip():
            found.append(Segment("".join(parts), starts, lines, field_name))
        parts, starts, lines, length = [], [], [], 0

    in_fence = False
    for number, raw in enumerate(text.splitlines(), start=1):
        if _FENCE.match(raw):
            in_fence = not in_fence
            flush()
            continue
        if in_fence:
            continue
        if not raw.strip():
            flush()
            continue
        cleaned = _clean_line(raw)
        if not cleaned.strip():
            continue
        if parts:
            parts.append(" ")
            length += 1
        starts.append(length)
        lines.append(number)
        parts.append(cleaned)
        length += len(cleaned)
    flush()
    return found
