"""Evaluation metrics (S16, design: اختيار النماذج والتقييم). Offline only, never in the pipeline.

Reference and hypothesis go through the same normalizer (`domain.text.normalize`, AC-2). CER and
WER divide the edit distance by the reference length. A hallucination is an item whose reference is
silent but whose hypothesis is not empty, or whose hypothesis has more than
`HALLUCINATION_RUN` consecutive insertions (design: Hallucination Rate).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from transcribe_engine.domain.text import normalize

__all__ = [
    "HALLUCINATION_RUN",
    "ItemResult",
    "cer",
    "hallucination_rate",
    "max_insertion_run",
    "wer",
]

HALLUCINATION_RUN = 5  # more than this many consecutive insertions counts as hallucinated


@dataclass(frozen=True)
class ItemResult:
    item_id: str
    ref: str
    hyp: str
    silent: bool


def cer(ref: str, hyp: str) -> float:
    reference = _chars(ref)
    hypothesis = _chars(hyp)
    return _rate(reference, hypothesis)


def wer(ref: str, hyp: str) -> float:
    return _rate(_words(ref), _words(hyp))


def max_insertion_run(ref: str, hyp: str) -> int:
    """The longest run of consecutive insertions in the word alignment of hyp against ref."""
    ops = _alignment(_words(ref), _words(hyp))
    longest = current = 0
    for op in ops:
        current = current + 1 if op == "I" else 0
        longest = max(longest, current)
    return longest


def hallucination_rate(items: Sequence[ItemResult]) -> float:
    if not items:
        return 0.0
    flagged = sum(1 for item in items if _hallucinated(item))
    return flagged / len(items)


def _hallucinated(item: ItemResult) -> bool:
    if item.silent and item.hyp.strip():
        return True
    return max_insertion_run(item.ref, item.hyp) > HALLUCINATION_RUN


def _chars(text: str) -> list[str]:
    return list(normalize(text).search)


def _words(text: str) -> list[str]:
    return normalize(text).search.split()


def _rate[T](reference: Sequence[T], hypothesis: Sequence[T]) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return _distance(reference, hypothesis) / len(reference)


def _distance[T](a: Sequence[T], b: Sequence[T]) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        current = [i]
        for j, y in enumerate(b, start=1):
            cost = 0 if x == y else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def _alignment[T](ref: Sequence[T], hyp: Sequence[T]) -> list[str]:
    """Edit operations from start to end: M match, S substitution, D deletion, I insertion."""
    n, m = len(ref), len(hyp)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        table[i][0] = i
    for j in range(m + 1):
        table[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            table[i][j] = min(table[i - 1][j] + 1, table[i][j - 1] + 1, table[i - 1][j - 1] + cost)
    ops: list[str] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and table[i][j] == table[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append("M" if ref[i - 1] == hyp[j - 1] else "S")
            i, j = i - 1, j - 1
        elif j > 0 and table[i][j] == table[i][j - 1] + 1:
            ops.append("I")
            j -= 1
        else:
            ops.append("D")
            i -= 1
    ops.reverse()
    return ops
