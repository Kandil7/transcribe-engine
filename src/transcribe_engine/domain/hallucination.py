"""Hallucination flags for ASR output (S12, design §4 فلتر الـ Hallucination).

A segment is flagged `suspect`, never deleted. Reasons:
- `repetition`: one word n-gram occurs at least `ngram_min_repeats` times in the segment, or the
  same n-gram opens or closes `ngram_min_repeats` adjacent segments in a row (across chunks).
- `known_phrase`: a phrase from the known-hallucination list occurs in the segment.
- `fast_speech`: more than `max_words_per_second` words per second of the segment's own span.

Text is compared after `domain.text.normalize()` only (CLAUDE.md: no ad-hoc Arabic regex).
Times are integer samples (ADR-0003); the rate is a parameter of each segment.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from transcribe_engine.domain.text import normalize

__all__ = [
    "FlaggedSegment",
    "HallucinationRules",
    "RawSegment",
    "flag_hallucinations",
]


@dataclass(frozen=True)
class RawSegment:
    text: str
    start_sample: int
    end_sample: int
    sample_rate: int


@dataclass(frozen=True)
class FlaggedSegment:
    segment: RawSegment
    suspect: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class HallucinationRules:
    known_phrases: frozenset[str] = field(default_factory=frozenset)
    max_words_per_second: float = 6.0  # Q1 of S12: proposed, tuned in S16
    ngram_size: int = 4  # Q1 of S12: proposed, tuned in S16
    ngram_min_repeats: int = 3  # Q1 of S12: proposed, tuned in S16


def flag_hallucinations(
    segments: Sequence[RawSegment], rules: HallucinationRules
) -> tuple[FlaggedSegment, ...]:
    words = [_words(segment.text) for segment in segments]
    grams = [_ngrams(w, rules.ngram_size) for w in words]
    across = _repeated_across(grams, rules.ngram_min_repeats)
    known = tuple(normalize(p).search for p in rules.known_phrases)
    flagged: list[FlaggedSegment] = []
    for idx, segment in enumerate(segments):
        reasons: list[str] = []
        if _repeats_within(grams[idx], rules.ngram_min_repeats) or idx in across:
            reasons.append("repetition")
        search = normalize(segment.text).search
        if any(phrase and phrase in search for phrase in known):
            reasons.append("known_phrase")
        if _too_fast(len(words[idx]), segment, rules.max_words_per_second):
            reasons.append("fast_speech")
        flagged.append(FlaggedSegment(segment, bool(reasons), tuple(reasons)))
    return tuple(flagged)


def _words(text: str) -> list[str]:
    return normalize(text).search.split()


def _ngrams(words: list[str], size: int) -> Counter[tuple[str, ...]]:
    if size < 1 or len(words) < size:
        return Counter()
    return Counter(tuple(words[i : i + size]) for i in range(len(words) - size + 1))


def _repeats_within(grams: Counter[tuple[str, ...]], min_repeats: int) -> bool:
    return any(count >= min_repeats for count in grams.values())


def _repeated_across(grams: list[Counter[tuple[str, ...]]], min_repeats: int) -> set[int]:
    """Indices of segments inside a run of at least `min_repeats` adjacent segments that share
    an n-gram."""
    flagged: set[int] = set()
    for gram in set().union(*grams):
        run: list[int] = []
        for idx, counter in enumerate(grams):
            if gram in counter:
                run.append(idx)
                continue
            if len(run) >= min_repeats:
                flagged.update(run)
            run = []
        if len(run) >= min_repeats:
            flagged.update(run)
    return flagged


def _too_fast(word_count: int, segment: RawSegment, max_words_per_second: float) -> bool:
    span = segment.end_sample - segment.start_sample
    if word_count == 0:
        return False
    if span <= 0:
        return True
    # words / (span / rate) > limit, rearranged to stay in integer samples where possible
    return word_count * segment.sample_rate > max_words_per_second * span
