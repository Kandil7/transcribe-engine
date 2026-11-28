"""Chapters and entities (S19, design: الإثراء). Pure domain logic.

- `snap_chapters`: an LLM's chapter times are never used as they come. Each start snaps to the
  nearest segment start, each end to the nearest segment end. A chapter whose snapped end is not
  after its start is dropped (AC-2).
- `verify_entities`: an entity is kept only if its text appears in the transcript. The rest are
  dropped and counted, so an invented name cannot reach a reader (AC-3).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from transcribe_engine.domain.transcript import Segment

__all__ = ["Chapter", "TimedEntity", "rule_chapters", "snap_chapters", "verify_entities"]


@dataclass(frozen=True)
class Chapter:
    title: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class TimedEntity:
    text: str
    start_ms: int


def snap_chapters(chapters: Sequence[Chapter], segments: Sequence[Segment]) -> tuple[Chapter, ...]:
    starts = sorted(segment.start_ms for segment in segments)
    ends = sorted(segment.end_ms for segment in segments)
    if not starts:
        return ()
    snapped: list[Chapter] = []
    for chapter in chapters:
        start = _nearest(starts, chapter.start_ms)
        end = _nearest(ends, chapter.end_ms)
        if end > start:
            snapped.append(Chapter(chapter.title, start, end))
    return tuple(snapped)


def verify_entities(
    entities: Sequence[TimedEntity], text: str
) -> tuple[tuple[TimedEntity, ...], int]:
    """The entities whose text occurs in `text`, and how many were dropped."""
    kept = tuple(e for e in entities if e.text and e.text in text)
    return kept, len(entities) - len(kept)


def _nearest(values: Sequence[int], target: int) -> int:
    return min(values, key=lambda value: (abs(value - target), value))


def rule_chapters(
    segments: Sequence[Segment], *, min_gap_ms: int = 2_000, min_chapter_ms: int = 30_000
) -> tuple[Chapter, ...]:
    """Chapters at the long pauses of a transcript, by rule (D-081: no LLM in v1).

    A chapter closes when the pause before the next segment is at least `min_gap_ms` and the chapter
    so far is at least `min_chapter_ms` long. The first chapter starts at 0, as YouTube requires.
    Each title is the first six words of the chapter, taken from the transcript itself."""
    if not segments:
        return ()
    groups: list[list[Segment]] = [[segments[0]]]
    for previous, segment in pairwise(segments):
        current = groups[-1]
        length = previous.end_ms - current[0].start_ms
        gap = segment.start_ms - previous.end_ms
        if gap >= min_gap_ms and length >= min_chapter_ms:
            groups.append([segment])
        else:
            current.append(segment)
    chapters: list[Chapter] = []
    for index, group in enumerate(groups):
        start = 0 if index == 0 else group[0].start_ms
        words = [word.text for segment in group for word in segment.words][:6]
        chapters.append(Chapter(" ".join(words), start, group[-1].end_ms))
    return tuple(chapters)
