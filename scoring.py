"""Word error rate and per-keyterm recall, with no external dependencies."""

from __future__ import annotations

import re

WORD = re.compile(r"[a-z0-9']+")


def normalize(text: str) -> list[str]:
    return WORD.findall(text.lower().replace("-", " "))


def wer(reference: str, hypothesis: str) -> float:
    """Word-level edit distance divided by reference length."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def term_hits(term: str, reference: str, hypothesis: str) -> tuple[int, int]:
    """(times the term appears in the transcript, times it was actually said), capped at said."""
    needle = normalize(term)

    def count(text: str) -> int:
        words = normalize(text)
        n = len(needle)
        return sum(words[i : i + n] == needle for i in range(len(words) - n + 1))

    said = count(reference)
    return min(count(hypothesis), said), said
