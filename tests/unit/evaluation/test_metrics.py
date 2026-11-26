"""S16 metrics (AC-1 known values, AC-2 normalizer on both sides, AC-3 hallucination definition).
Each rule has a positive control on the same function, so a metric that is always 0 or always 1
cannot pass. Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def test_cer_wer_known_values() -> None:
    """AC-1: textbook and Arabic cases. CER and WER divide the edit distance by the reference
    length. Positive control: a different hypothesis gives a different, non-zero score."""
    metrics = _mod("evaluation.metrics")
    assert metrics.cer("kitten", "sitting") == pytest.approx(0.5)  # 3 edits over 6 characters
    assert metrics.wer("the cat sat on the mat", "the cat sat on mat") == pytest.approx(1 / 6)
    assert metrics.cer("كتاب", "كتب") == pytest.approx(0.25)  # one missing letter over four
    assert metrics.cer("كتاب", "كتاب") == 0.0
    assert metrics.cer("", "") == 0.0
    assert metrics.cer("", "x") == 1.0


def test_normalizer_applied_both_sides() -> None:
    """AC-2: hamza, alef and diacritic differences score 0, because the same normalizer runs on the
    reference and the hypothesis. Positive control: a real letter difference still scores."""
    metrics = _mod("evaluation.metrics")
    assert metrics.cer("أحمد", "احمد") == 0.0
    assert metrics.cer("إلى", "الى") == 0.0
    assert metrics.cer("كَتَبَ", "كتب") == 0.0
    assert metrics.cer("كتب", "كتاب") > 0.0
    assert metrics.wer("أحمد يكتب", "احمد يكتب") == 0.0


def test_hallucination_rate_definition() -> None:
    """AC-3: an item is hallucinated when its reference is silent and the hypothesis is not empty,
    or when the hypothesis has more than 5 consecutive insertions. Positive control: the clean
    items are not counted, and an all-clean set gives 0."""
    metrics = _mod("evaluation.metrics")
    items = [
        metrics.ItemResult("silent-with-text", ref="", hyp="شكرا", silent=True),
        metrics.ItemResult("silent-empty", ref="", hyp="", silent=True),
        metrics.ItemResult("clean", ref="كلام عادي", hyp="كلام عادي", silent=False),
        metrics.ItemResult("run-of-six", ref="a b", hyp="a b x x x x x x", silent=False),
    ]
    assert metrics.hallucination_rate(items) == pytest.approx(0.5)
    clean = [metrics.ItemResult("c", ref="a b", hyp="a b", silent=False)]
    assert metrics.hallucination_rate(clean) == 0.0
    assert metrics.max_insertion_run("a b", "a b x x x x x x") == 6
