"""Consented training manifest (S22, design: التصحيح البشري وبيانات التدريب). Pure domain logic.

A segment is exported only when its audio is consented (S21 flag, AC-5). Corrected segments are
exported even below the confidence threshold, because a person checked them. Each line has exactly
the seven fields of the spec (AC-6).
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from transcribe_engine.domain.transcript import Segment

__all__ = ["ManifestLine", "TrainingSegment", "export_manifest"]


@dataclass(frozen=True)
class TrainingSegment:
    segment: Segment
    audio: str
    source: str
    snr_db: float | None
    lang: str
    consented: bool
    corrected: bool


@dataclass(frozen=True)
class ManifestLine:
    audio: str
    offset_ms: int
    duration_ms: int
    text: str
    source: str
    snr_db: float | None
    lang: str


def export_manifest(items: Iterable[TrainingSegment], *, min_conf: float) -> Iterator[ManifestLine]:
    for item in items:
        if not item.consented:
            continue
        if not item.corrected and _confidence(item.segment) < min_conf:
            continue
        yield ManifestLine(
            audio=item.audio,
            offset_ms=item.segment.start_ms,
            duration_ms=item.segment.end_ms - item.segment.start_ms,
            text=" ".join(word.text for word in item.segment.words),
            source=item.source,
            snr_db=item.snr_db,
            lang=item.lang,
        )


def _confidence(segment: Segment) -> float:
    confidences = [word.conf for word in segment.words if word.conf is not None]
    return sum(confidences) / len(confidences) if confidences else 0.0
