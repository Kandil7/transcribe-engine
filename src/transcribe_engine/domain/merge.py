"""Ordered merge of chunk results (S10). Pure domain logic.

Rules (design: التجميع):
- Every chunk of the plan has exactly one result. A missing or duplicate result is refused.
- A word is kept only when its midpoint lies in its chunk's core. Padding is reported by both
  neighbours, so each word survives once (midpoint rule).
- Output is sorted by time, then by chunk, so result order never changes the output.
- Times leave the pipeline as integer ms: floor(samples × 1000 / sample_rate).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil

from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError

__all__ = [
    "ChunkResult",
    "MergeError",
    "MergedWords",
    "RawWord",
    "Word",
    "merge",
    "validate_merge",
]


class MergeError(PermanentError):
    """The chunk results do not match the plan. Maps to a permanent failure of the job."""

    code = "merge_error"


@dataclass(frozen=True)
class RawWord:
    """A word as the ASR reports it: local sample offsets from the start of the padded window."""

    text: str
    local_start: int
    local_end: int
    conf: float | None


@dataclass(frozen=True)
class ChunkResult:
    chunk_idx: int
    words: tuple[RawWord, ...]


@dataclass(frozen=True)
class Word:
    """A merged word in the file's time base, integer milliseconds."""

    text: str
    start_ms: int
    end_ms: int
    conf: float | None
    chunk_idx: int
    speaker: str | None = None  # set by diarization (S17); None when not diarized
    overlap: bool = False  # True when the word overlaps speech of two speakers (S17)


@dataclass(frozen=True)
class MergedWords:
    words: tuple[Word, ...]
    sample_rate: int  # 0 when the plan has no chunks (silent file)


def _ms(sample: int, sample_rate: int) -> int:
    return sample * 1000 // sample_rate


def merge(chunks: Sequence[Chunk], results: Sequence[ChunkResult]) -> MergedWords:
    """Merge the results of every chunk into one ordered word list.

    Raises MergeError when the plan is inconsistent, a result is missing or duplicated, or a result
    names a chunk the plan does not have.
    """
    if not chunks:
        if results:
            raise MergeError("results were reported for a plan with no chunks")
        return MergedWords(words=(), sample_rate=0)
    by_idx = _index_plan(chunks)
    by_result = _index_results(results, by_idx)
    rate = chunks[0].sample_rate
    words: list[Word] = []
    for idx in sorted(by_idx):
        words.extend(_kept_words(by_idx[idx], by_result[idx], rate))
    words.sort(key=lambda word: (word.start_ms, word.end_ms, word.chunk_idx))
    return MergedWords(words=tuple(words), sample_rate=rate)


def _index_plan(chunks: Sequence[Chunk]) -> dict[int, Chunk]:
    total = chunks[0].total
    if len(chunks) != total or any(chunk.total != total for chunk in chunks):
        raise MergeError("chunk plan is inconsistent")
    by_idx = {chunk.idx: chunk for chunk in chunks}
    if sorted(by_idx) != list(range(total)):
        raise MergeError("chunk plan has missing or duplicate indexes")
    return by_idx


def _index_results(
    results: Sequence[ChunkResult], by_idx: dict[int, Chunk]
) -> dict[int, ChunkResult]:
    by_result: dict[int, ChunkResult] = {}
    for result in results:
        if result.chunk_idx in by_result:
            raise MergeError("a chunk has more than one result")
        by_result[result.chunk_idx] = result
    if set(by_result) != set(by_idx):
        raise MergeError("chunk results do not match the plan")
    return by_result


def _kept_words(chunk: Chunk, result: ChunkResult, rate: int) -> list[Word]:
    """The words of one chunk whose midpoint falls inside its core (midpoint rule)."""
    origin = chunk.start_sample - chunk.pad_before
    kept: list[Word] = []
    for raw in result.words:
        if raw.local_start < 0 or raw.local_end < raw.local_start:
            raise MergeError("a word has invalid bounds")
        global_start = origin + raw.local_start
        global_end = origin + raw.local_end
        midpoint = (global_start + global_end) // 2
        if chunk.start_sample <= midpoint < chunk.end_sample:
            kept.append(
                Word(
                    text=raw.text,
                    start_ms=_ms(global_start, rate),
                    end_ms=_ms(global_end, rate),
                    conf=raw.conf,
                    chunk_idx=chunk.idx,
                )
            )
    return kept


def validate_merge(words: MergedWords, duration_samples: int) -> list[str]:
    """Warnings about a merged transcript. Returns an empty list when nothing is wrong.

    Checks: no word ends before it starts, times never go backwards, and no word ends after the
    file. The words are not changed; the caller decides what a warning means.
    """
    if words.sample_rate == 0:
        return []
    limit_ms = ceil(duration_samples * 1000 / words.sample_rate)
    problems: list[str] = []
    previous_start = -1
    for word in words.words:
        if word.end_ms < word.start_ms:
            problems.append(f"word from chunk {word.chunk_idx} ends before it starts")
        if word.start_ms < previous_start:
            problems.append(f"word from chunk {word.chunk_idx} is out of time order")
        if word.end_ms > limit_ms:
            problems.append(f"word from chunk {word.chunk_idx} ends beyond the file duration")
        previous_start = word.start_ms
    return problems
