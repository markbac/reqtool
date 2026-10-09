"""Near-duplicate requirement detection."""

from __future__ import annotations

import math
import re
from typing import Any

from reqtool.store import Store


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"\w+", text.lower()) if len(w) > 3)


def detect_duplicate_requirements(store: Store, threshold: float = 0.5) -> list[dict[str, Any]]:
    """Find pairs of live requirements whose title and description share enough words (Jaccard similarity).

    Exact, but not quadratic: each item is tokenised once, and prefix filtering over a global
    rarest-first token order means only pairs that share a rare token are compared
    (a pair with Jaccard >= t must share a token in the first |a| - ceil(t*|a|) + 1 tokens of each).
    """
    return [dict(d) for d in store.memo("duplicates", threshold, lambda: _find_duplicates(store, threshold))]


def _find_duplicates(store: Store, threshold: float) -> list[dict[str, Any]]:
    reqs = [r for r in store.requirements.values() if not r.get("deleted")]
    tokens = [_tokenize(f"{r.get('title') or ''} {(r.get('content') or {}).get('description') or ''}") for r in reqs]

    freq: dict[str, int] = {}
    for token_set in tokens:
        for t in token_set:
            freq[t] = freq.get(t, 0) + 1
    order = lambda t: (freq[t], t)  # rarest first, ties broken by text so the order is total

    ranked = [sorted(toks, key=order) for toks in tokens]
    postings: dict[str, list[int]] = {}
    found: list[tuple[float, int, int, frozenset[str]]] = []

    for i, toks in enumerate(ranked):
        n = len(toks)
        if not n:
            continue
        prefix_len = n - math.ceil(threshold * n) + 1 if threshold > 0 else n
        candidates: set[int] = set()
        for t in toks[:max(prefix_len, 1)]:
            candidates.update(postings.get(t, ()))
        a = tokens[i]
        for j in candidates:
            b = tokens[j]
            if len(b) < threshold * n or n < threshold * len(b):
                continue  # sizes too different to reach the threshold
            inter = a & b
            similarity = len(inter) / (n + len(b) - len(inter))
            if similarity >= threshold:
                found.append((similarity, j, i, inter))
        for t in toks[:max(prefix_len, 1)]:
            postings.setdefault(t, []).append(i)

    duplicates = []
    for similarity, j, i, inter in sorted(found, key=lambda f: (-round(f[0], 2), f[1], f[2])):
        r1, r2 = reqs[j], reqs[i]
        duplicates.append({
            "req_a": {"uid": r1["uid"], "id": r1["id"], "title": r1["title"]},
            "req_b": {"uid": r2["uid"], "id": r2["id"], "title": r2["title"]},
            "similarity_score": round(similarity, 2),
            "overlapping_terms": sorted(inter)[:8],
        })
    return duplicates


def suggest_duplicates(store: Store, title: str, description: str = "", exclude_uid: str | None = None,
                       threshold: float = 0.4, limit: int = 5) -> list[dict[str, Any]]:
    """Existing requirements that resemble text being typed now, best first (ENH-05)."""
    mine = _tokenize(f"{title or ''} {description or ''}")
    if not mine:
        return []
    out = []
    for r in store.requirements.values():
        if r.get("deleted") or r["uid"] == exclude_uid:
            continue
        theirs = _tokenize(f"{r.get('title') or ''} {(r.get('content') or {}).get('description') or ''}")
        union = mine | theirs
        score = len(mine & theirs) / len(union) if union else 0.0
        if score >= threshold:
            out.append({"uid": r["uid"], "id": r.get("id"), "title": r.get("title", ""), "status": r.get("status"),
                        "similarity_score": round(score, 2), "overlapping_terms": sorted(mine & theirs)[:8]})
    return sorted(out, key=lambda d: -d["similarity_score"])[:limit]


class DuplicateDetector:
    """The boundary callers depend on, so the algorithm can change without touching them (ARC-14)."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def find(self, store: Store) -> list[dict[str, Any]]:
        return detect_duplicate_requirements(store, self.threshold)
