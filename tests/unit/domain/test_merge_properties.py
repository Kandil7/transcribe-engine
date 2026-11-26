"""S10 merge properties (AC-1 shuffle invariance, AC-2 split and merge preserves times).

Hypothesis generates the layouts. The merge must not depend on result order, and cutting ground
truth into padded chunks and merging must give back the same words, to zero samples.
Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
import random
from types import ModuleType
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

PAD = 200
MAX = 1_000
RATE = 1000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


@st.composite
def layouts(draw: Any) -> tuple[list[tuple[int, int]], int, list[tuple[int, int]]]:
    """Speech regions, total length, and ground-truth words inside the regions (length <= PAD)."""
    regions: list[tuple[int, int]] = []
    words: list[tuple[int, int]] = []
    cursor = 0
    for _ in range(draw(st.integers(1, 4))):
        start = cursor + draw(st.integers(0, 600))
        end = start + draw(st.integers(PAD // 2, 2_500))
        regions.append((start, end))
        position = start
        while position + PAD // 2 <= end:
            begin = position + draw(st.integers(0, 150))
            if begin + PAD // 2 > end:
                break
            words.append((begin, begin + PAD // 2))
            position = begin + PAD // 2
        cursor = end
    total = cursor + draw(st.integers(0, 600))
    return regions, total, words


def _plan(regions: list[tuple[int, int]], total: int) -> tuple[Any, ...]:
    chunks = _mod("transcribe_engine.domain.chunks")
    spans = [chunks.SpeechRegion(start, end) for start, end in regions]
    return chunks.plan_chunks(
        spans,
        max_samples=MAX,
        pad=PAD,
        total_samples=total,
        sample_rate=RATE,
        media_sha256="a" * 64,
        config_hash="b" * 64,
        job_id="job-1",
    )


def _results_for(chunks: tuple[Any, ...], words: list[tuple[int, int]]) -> list[Any]:
    """What a perfect ASR would return per chunk: every ground-truth word inside the padded
    window, in that chunk's local sample coordinates."""
    merge = _mod("transcribe_engine.domain.merge")
    results = []
    for chunk in chunks:
        origin = chunk.start_sample - chunk.pad_before
        window_end = chunk.end_sample + chunk.pad_after
        local = tuple(
            merge.RawWord(f"w{start}", start - origin, end - origin, None)
            for start, end in words
            if start >= origin and end <= window_end
        )
        results.append(merge.ChunkResult(chunk.idx, local))
    return results


@settings(max_examples=100, deadline=None)
@given(layout=layouts(), seed=st.integers(0, 2**32))
def test_completion_order_irrelevant(layout: tuple[Any, ...], seed: int) -> None:
    """AC-1. Results arrive in any order; the merged output is identical (100 shuffles)."""
    merge = _mod("transcribe_engine.domain.merge")
    regions, total, words = layout
    chunks = _plan(regions, total)
    results = _results_for(chunks, words)
    baseline = merge.merge(chunks, results)
    shuffled = list(results)
    random.Random(seed).shuffle(shuffled)
    assert merge.merge(chunks, shuffled) == baseline


@settings(max_examples=100, deadline=None)
@given(layout=layouts())
def test_split_merge_preserves_times(layout: tuple[Any, ...]) -> None:
    """AC-2. Cutting the audio into padded chunks and merging returns every ground-truth word with
    exactly its original start and end (zero-sample tolerance)."""
    merge = _mod("transcribe_engine.domain.merge")
    regions, total, words = layout
    chunks = _plan(regions, total)
    merged = merge.merge(chunks, _results_for(chunks, words))
    got = sorted((w.start_ms, w.end_ms) for w in merged.words)
    assert got == sorted(words)
