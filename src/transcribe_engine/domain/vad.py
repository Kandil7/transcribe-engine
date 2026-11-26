"""Cut and merge of speech regions into chunk spans (S11). Pure domain logic, integer samples.

Rules (design: VAD مع Cut & Merge):
- Adjacent regions merge while the span stays within the target length; a gap between regions is
  where a span ends. Spans therefore never cut a speech region in the middle, unless it is longer
  than the maximum.
- A span longer than the maximum is cut at the midpoint of its longest internal silence. The
  cut repeats until every piece fits.
- Only when no silence lies inside a too-long span does a fixed window apply: windows of the
  maximum length, stepping by (maximum - overlap). Each later window records its overlap.
- Padding is not applied here; the planner pads each core inside the file (D-032).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from transcribe_engine.domain.chunks import SpeechRegion

__all__ = ["SampleSpan", "VadParams", "cut_and_merge"]


@dataclass(frozen=True)
class SampleSpan:
    start_sample: int
    end_sample: int
    overlap_with_prev: int = 0

    def __post_init__(self) -> None:
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("span must satisfy 0 <= start < end")


@dataclass(frozen=True)
class VadParams:
    """Detector parameters, kept in PipelineConfig.vad_params so they enter the result key."""

    threshold: float
    min_silence_ms: int
    min_speech_ms: int


def cut_and_merge(  # noqa: PLR0913 - the spec's keyword-only signature (S11)
    regions: Sequence[SpeechRegion],
    *,
    target_ms: int,
    max_ms: int,
    pad_ms: int,
    overlap_ms: int,
    silences: Sequence[SampleSpan],
    sample_rate: int,
) -> tuple[SampleSpan, ...]:
    """Spans that cover every speech sample, each no longer than max_ms.

    Raises ValueError when the limits are inconsistent: target must not exceed the maximum, the pad
    must be smaller than the maximum, and the overlap must be smaller than the maximum.
    """
    if not 0 < target_ms <= max_ms or sample_rate <= 0:
        raise ValueError("need 0 < target_ms <= max_ms and a positive sample rate")
    if not 0 <= pad_ms < max_ms or not 0 <= overlap_ms < max_ms:
        raise ValueError("pad and overlap must be non-negative and smaller than the maximum")
    target = _samples(target_ms, sample_rate)
    cap = _samples(max_ms, sample_rate)
    overlap = _samples(overlap_ms, sample_rate)
    spans: list[SampleSpan] = []
    for start, end in _group(regions, target):
        spans.extend(_split(start, end, cap, overlap, silences))
    return tuple(spans)


def _samples(milliseconds: int, sample_rate: int) -> int:
    return milliseconds * sample_rate // 1000


def _group(regions: Sequence[SpeechRegion], target: int) -> list[tuple[int, int]]:
    """Greedy merge: extend the current span while it stays within the target."""
    groups: list[tuple[int, int]] = []
    current: tuple[int, int] | None = None
    for region in regions:
        if current is None:
            current = (region.start_sample, region.end_sample)
        elif region.end_sample - current[0] <= target:
            current = (current[0], region.end_sample)
        else:
            groups.append(current)
            current = (region.start_sample, region.end_sample)
    if current is not None:
        groups.append(current)
    return groups


def _split(
    start: int, end: int, cap: int, overlap: int, silences: Sequence[SampleSpan]
) -> list[SampleSpan]:
    if end - start <= cap:
        return [SampleSpan(start, end)]
    inside = [s for s in silences if s.start_sample > start and s.end_sample < end]
    if inside:
        longest = max(inside, key=lambda s: (s.end_sample - s.start_sample, -s.start_sample))
        cut = (longest.start_sample + longest.end_sample) // 2
        return _split(start, cut, cap, overlap, silences) + _split(cut, end, cap, overlap, silences)
    return _windows(start, end, cap, overlap)


def _windows(start: int, end: int, cap: int, overlap: int) -> list[SampleSpan]:
    step = cap - overlap
    windows: list[SampleSpan] = []
    position = start
    previous_end: int | None = None
    while True:
        window_end = min(end, position + cap)
        shared = (
            previous_end - position if previous_end is not None and previous_end > position else 0
        )
        windows.append(SampleSpan(position, window_end, shared))
        if window_end >= end:
            return windows
        previous_end = window_end
        position += step
