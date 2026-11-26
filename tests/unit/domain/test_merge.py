"""S10 merge rules (AC-3 midpoint rule, AC-4 missing idx) and validation. Pure domain.

Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _two_overlapping_chunks() -> tuple[object, object]:
    """Core [0, 1000) padded to 1200 on the right, and core [1000, 2000) padded to 800 on the left.
    Sample rate 1000 makes samples equal milliseconds, so the test reads directly."""
    chunks = _mod("transcribe_engine.domain.chunks")
    common = {
        "job_id": "job-1",
        "total": 2,
        "sample_rate": 1000,
        "media_sha256": "a" * 64,
        "config_hash": "b" * 64,
    }
    first = chunks.Chunk(
        chunk_id="c0",
        idx=0,
        start_sample=0,
        end_sample=1_000,
        pad_before=0,
        pad_after=200,
        **common,
    )
    second = chunks.Chunk(
        chunk_id="c1",
        idx=1,
        start_sample=1_000,
        end_sample=2_000,
        pad_before=200,
        pad_after=0,
        **common,
    )
    return first, second


@pytest.mark.xfail(strict=True, reason="S10")
def test_midpoint_rule_dedupes_padding() -> None:
    """AC-3. A word in the overlap (global 900..1100, midpoint 1000) is kept once, by the chunk
    whose core holds its midpoint. The same word reported by the other chunk is dropped."""
    merge = _mod("transcribe_engine.domain.merge")
    first, second = _two_overlapping_chunks()
    # Chunk 0 (origin 0) sees the word at local 900..1100. Midpoint 1000 is not in [0, 1000).
    from_first = merge.ChunkResult(0, (merge.RawWord("ايوه", 900, 1_100, None),))
    # Chunk 1's audio starts at global 800. Local 100..300 is global 900..1100 (midpoint in core).
    from_second = merge.ChunkResult(1, (merge.RawWord("ايوه", 100, 300, None),))
    merged = merge.merge((first, second), (from_first, from_second))
    assert [(w.text, w.start_ms, w.end_ms, w.chunk_idx) for w in merged.words] == [
        ("ايوه", 900, 1_100, 1),
    ]


@pytest.mark.xfail(strict=True, reason="S10")
def test_missing_idx_raises() -> None:
    """AC-4. A merge with a missing chunk result is refused; partial output is never returned."""
    merge = _mod("transcribe_engine.domain.merge")
    first, second = _two_overlapping_chunks()
    with pytest.raises(merge.MergeError):
        merge.merge((first, second), (merge.ChunkResult(0, ()),))


@pytest.mark.xfail(strict=True, reason="S10")
def test_duplicate_result_raises() -> None:
    """A chunk reported twice is a bookkeeping bug. Refuse it, do not guess which copy is right."""
    merge = _mod("transcribe_engine.domain.merge")
    first, second = _two_overlapping_chunks()
    with pytest.raises(merge.MergeError):
        merge.merge(
            (first, second),
            (merge.ChunkResult(0, ()), merge.ChunkResult(0, ()), merge.ChunkResult(1, ())),
        )


@pytest.mark.xfail(strict=True, reason="S10")
def test_validation_flags_words_beyond_the_duration() -> None:
    """Validation returns warnings, not exceptions: a word ending after the file's duration."""
    merge = _mod("transcribe_engine.domain.merge")
    words = merge.MergedWords(
        words=(
            merge.Word("a", 0, 500, None, 0),
            merge.Word("b", 500, 1_500, None, 1),
        ),
        sample_rate=1000,
    )
    problems = merge.validate_merge(words, duration_samples=1_000)
    assert any("beyond" in problem for problem in problems)
    assert merge.validate_merge(words, duration_samples=2_000) == []
