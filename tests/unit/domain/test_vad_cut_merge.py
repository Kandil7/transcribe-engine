"""S11 cut-and-merge rules (AC-3 longest silence, AC-4 fixed window only without silence) and the
properties behind AC-1 (every speech sample covered) and AC-2 (no span longer than the maximum).

Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

RATE = 16_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _s(seconds: float) -> int:
    return round(seconds * RATE)


def _regions(spans: list[tuple[float, float]]) -> list[Any]:
    chunks = _mod("transcribe_engine.domain.chunks")
    return [chunks.SpeechRegion(_s(a), _s(b)) for a, b in spans]


def _silences(spans: list[tuple[float, float]]) -> list[Any]:
    vad = _mod("transcribe_engine.domain.vad")
    return [vad.SampleSpan(_s(a), _s(b)) for a, b in spans]


def _cut(
    regions: list[Any], silences: list[Any], *, target: float, maximum: float, overlap: float = 1.5
) -> tuple[Any, ...]:
    vad = _mod("transcribe_engine.domain.vad")
    return vad.cut_and_merge(
        regions,
        target_ms=int(target * 1000),
        max_ms=int(maximum * 1000),
        pad_ms=200,
        overlap_ms=int(overlap * 1000),
        silences=silences,
        sample_rate=RATE,
    )


@pytest.mark.xfail(strict=True, reason="S11")
def test_cut_at_longest_silence() -> None:
    """AC-3. A 30 s speech region with two internal silences, longest (10 to 11.5 s) first, is cut
    at the midpoint of the longest silence, then at the next silence that keeps pieces
    under 12 s."""
    spans = _cut(_regions([(0, 30)]), _silences([(10, 11.5), (20, 21)]), target=12, maximum=12)
    assert [(s.start_sample, s.end_sample) for s in spans] == [
        (0, _s(10.75)),
        (_s(10.75), _s(20.5)),
        (_s(20.5), _s(30)),
    ]


@pytest.mark.xfail(strict=True, reason="S11")
def test_fixed_window_only_without_silence() -> None:
    """AC-4. With no silence inside a 30 s region, windows of 12 s step by 10.5 s (1.5 s overlap)
    and each later window records its overlap with the previous one."""
    spans = _cut(_regions([(0, 30)]), [], target=12, maximum=12, overlap=1.5)
    assert [(s.start_sample, s.end_sample) for s in spans] == [
        (0, _s(12)),
        (_s(10.5), _s(22.5)),
        (_s(21), _s(30)),
    ]
    assert [s.overlap_with_prev for s in spans] == [0, _s(1.5), _s(1.5)]


@pytest.mark.xfail(strict=True, reason="S11")
def test_adjacent_regions_merge_up_to_the_target() -> None:
    """Regions close together merge into one span up to the target. Beyond it, the gap cuts."""
    spans = _cut(_regions([(0, 3), (4, 6), (20, 22)]), [], target=10, maximum=12)
    assert [(s.start_sample, s.end_sample) for s in spans] == [(0, _s(6)), (_s(20), _s(22))]


@pytest.mark.xfail(strict=True, reason="S11")
@settings(max_examples=200, deadline=None)
@given(
    data=st.data(),
    count=st.integers(1, 6),
)
def test_every_speech_sample_covered_and_no_span_too_long(data: Any, count: int) -> None:
    """AC-1 and AC-2. Every speech sample lies in some span, and no span exceeds the maximum."""
    regions: list[tuple[float, float]] = []
    cursor = 0.0
    for _ in range(count):
        gap = data.draw(st.floats(0.0, 4.0))
        length = data.draw(st.floats(0.5, 40.0))
        regions.append((cursor + gap, cursor + gap + length))
        cursor = cursor + gap + length
    silences = [
        (a, a + data.draw(st.floats(0.2, 3.0)))
        for a in data.draw(st.lists(st.floats(0.0, cursor), max_size=6))
    ]
    spans = _cut(_regions(regions), _silences(silences), target=20, maximum=24)
    assert all(s.end_sample - s.start_sample <= _s(24) for s in spans)
    for a, b in regions:
        for sample in (_s(a), _s(b) - 1):
            assert any(s.start_sample <= sample < s.end_sample for s in spans)
