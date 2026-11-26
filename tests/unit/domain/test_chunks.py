"""S10 chunk plan (AC-5 edge cases and plan invariants). Pure domain, no I/O.

Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
import itertools
from types import ModuleType

import pytest

RATE = 16_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _plan(
    regions: list[tuple[int, int]],
    *,
    max_samples: int = 160_000,
    pad: int = 8_000,
    total: int = 1_600_000,
) -> tuple[object, ...]:
    chunks = _mod("transcribe_engine.domain.chunks")
    spans = [chunks.SpeechRegion(start, end) for start, end in regions]
    return chunks.plan_chunks(
        spans,
        max_samples=max_samples,
        pad=pad,
        total_samples=total,
        sample_rate=RATE,
        media_sha256="a" * 64,
        config_hash="b" * 64,
        job_id="job-1",
    )


@pytest.mark.xfail(strict=True, reason="S10")
def test_silent_file_has_no_chunks() -> None:
    """AC-5. No speech regions, no chunks. Positive control: one region gives one chunk."""
    assert _plan([]) == ()
    assert len(_plan([(1_000, 5_000)])) == 1


@pytest.mark.xfail(strict=True, reason="S10")
def test_single_chunk_is_padded_inside_the_file() -> None:
    """AC-5. A short region in the middle of the file gets padding on both sides."""
    (chunk,) = _plan([(100_000, 120_000)], total=400_000)
    assert (chunk.idx, chunk.total) == (0, 1)
    assert (chunk.start_sample, chunk.end_sample) == (100_000, 120_000)
    assert (chunk.pad_before, chunk.pad_after) == (8_000, 8_000)


@pytest.mark.xfail(strict=True, reason="S10")
def test_padding_is_clipped_at_file_edges() -> None:
    """AC-5. A region at the very start has no room before it, and at the end none after it."""
    (chunk,) = _plan([(0, 5_000)], total=5_000)
    assert (chunk.pad_before, chunk.pad_after) == (0, 0)


@pytest.mark.xfail(strict=True, reason="S10")
def test_region_longer_than_max_is_split_into_cores() -> None:
    """AC-5. A region longer than max_samples is cut into consecutive cores of at most max."""
    chunks = _plan([(0, 400_000)], max_samples=160_000)
    assert [(c.start_sample, c.end_sample) for c in chunks] == [
        (0, 160_000),
        (160_000, 320_000),
        (320_000, 400_000),
    ]
    assert [c.idx for c in chunks] == [0, 1, 2]
    assert all(c.total == 3 for c in chunks)


@pytest.mark.xfail(strict=True, reason="S10")
def test_plan_invariants_hold_for_many_regions() -> None:
    """Cores are sorted, disjoint and cover all speech. Ids are unique and deterministic."""
    regions = [(1_000, 50_000), (60_000, 61_000), (200_000, 420_000)]
    chunks = _plan(regions, max_samples=100_000)
    cores = [(c.start_sample, c.end_sample) for c in chunks]
    assert cores == sorted(cores)
    assert all(prev_end <= start for (_, prev_end), (start, _) in itertools.pairwise(cores))
    covered = sum(end - start for start, end in cores)
    assert covered == sum(end - start for start, end in regions)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(c.pad_before <= 8_000 and c.pad_after <= 8_000 for c in chunks)
    again = _plan(regions, max_samples=100_000)
    assert [c.chunk_id for c in again] == [c.chunk_id for c in chunks]


@pytest.mark.xfail(strict=True, reason="S10")
def test_invalid_inputs_are_refused() -> None:
    """Overlapping regions and non-positive limits are programming errors, not silent output."""
    with pytest.raises(ValueError, match="overlap"):
        _plan([(0, 10_000), (5_000, 20_000)])
    with pytest.raises(ValueError, match="positive"):
        _plan([(0, 1_000)], max_samples=0)
