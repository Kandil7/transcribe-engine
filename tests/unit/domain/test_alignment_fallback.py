"""S14 AC-4 (D-077): when alignment fails, the words are spread over the segment in order.

Positive control: the words cover the segment from its start to its end, in order, and a longer
word takes a longer span. Empty text gives no words.
"""

import importlib
from itertools import pairwise
from types import ModuleType


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.alignment_fallback")


def test_words_spread_over_the_segment_in_order() -> None:
    fallback = _mod()
    words = fallback.segment_times("alpha beta", 1_000, 3_000)
    assert [w.text for w in words] == ["alpha", "beta"]
    assert words[0].local_start == 1_000
    assert words[-1].local_end == 3_000
    assert all(w.fallback for w in words)
    assert all(a.local_end <= b.local_start for a, b in pairwise(words))


def test_a_longer_word_takes_a_longer_span() -> None:
    fallback = _mod()
    short, long = fallback.segment_times("ab abcdefghij", 0, 10_000)
    assert (long.local_end - long.local_start) > (short.local_end - short.local_start)


def test_empty_text_gives_no_words() -> None:
    assert _mod().segment_times("   ", 0, 100) == ()
