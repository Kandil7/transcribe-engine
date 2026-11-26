"""Chunk plan (S10): split speech regions into consecutive cores, each padded inside the file.

Pure domain logic. Times are integer samples (ADR-0003). A chunk's core is the span it owns in the
merged transcript. Its padding is audio the ASR also sees, so words that straddle a boundary are
reported by both neighbours and the merge keeps each one once (midpoint rule, merge.py).

Decision D-032: one chunk per speech-region piece. Regions are not packed together across gaps.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from transcribe_engine.domain.keys import chunk_id

__all__ = ["NORMALIZED_SAMPLE_RATE", "Chunk", "SpeechRegion", "plan_chunks"]

# The normalized audio is 16 kHz mono PCM (S09, ADR-0003).
NORMALIZED_SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class SpeechRegion:
    start_sample: int
    end_sample: int

    def __post_init__(self) -> None:
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("speech region must satisfy 0 <= start < end")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    job_id: str
    idx: int
    total: int
    start_sample: int  # core start (inclusive), in the normalized file
    end_sample: int  # core end (exclusive)
    pad_before: int
    pad_after: int
    sample_rate: int
    media_sha256: str
    config_hash: str
    overlap_with_prev: int = 0


def plan_chunks(  # noqa: PLR0913 - the spec's keyword-only signature (S10, D-032)
    regions: Sequence[SpeechRegion],
    *,
    max_samples: int,
    pad: int,
    total_samples: int,
    sample_rate: int,
    media_sha256: str,
    config_hash: str,
    job_id: str,
) -> tuple[Chunk, ...]:
    """Cut each region into cores of at most `max_samples`, pad each core inside the file.

    Raises ValueError for overlapping or unsorted regions, regions outside the file, or limits that
    are not positive. Silence (no regions) gives an empty plan.
    """
    if max_samples <= 0 or sample_rate <= 0:
        raise ValueError("max_samples and sample_rate must be positive")
    if pad < 0 or total_samples < 0:
        raise ValueError("pad and total_samples must not be negative")
    previous_end = 0
    for region in regions:
        if region.start_sample < previous_end:
            raise ValueError("speech regions must be sorted and must not overlap")
        if region.end_sample > total_samples:
            raise ValueError("speech region extends past the end of the file")
        previous_end = region.end_sample

    cores: list[tuple[int, int]] = []
    for region in regions:
        start = region.start_sample
        while start < region.end_sample:
            end = min(region.end_sample, start + max_samples)
            cores.append((start, end))
            start = end

    total = len(cores)
    return tuple(
        Chunk(
            chunk_id=chunk_id(media_sha256, config_hash, idx, start, end),
            job_id=job_id,
            idx=idx,
            total=total,
            start_sample=start,
            end_sample=end,
            pad_before=min(pad, start),
            pad_after=min(pad, total_samples - end),
            sample_rate=sample_rate,
            media_sha256=media_sha256,
            config_hash=config_hash,
        )
        for idx, (start, end) in enumerate(cores)
    )
