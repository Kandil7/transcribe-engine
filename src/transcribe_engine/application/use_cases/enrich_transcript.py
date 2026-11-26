"""Enrich one transcript version (S19, design: الإثراء). The transcript is never changed (AC-4).

Each artifact runs on its own. A TransientError or PermanentError from one is recorded in `failures`
and the others still come back (AC-5). Entities are checked against the transcript text (AC-3), and
chapter times are snapped to the segments (AC-2).
"""

from dataclasses import dataclass

from transcribe_engine.application.ports.enricher import Enricher
from transcribe_engine.domain.chapters import Chapter, snap_chapters, verify_entities
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.domain.transcript import CanonicalTranscript

__all__ = ["EnrichTranscript", "EnrichmentResult", "transcript_text"]

DEFAULT_SUMMARY_WORDS = 120


@dataclass(frozen=True)
class EnrichmentResult:
    chapters: tuple[Chapter, ...]
    summary: str | None
    entities: tuple[str, ...]
    dropped_entities: int
    failures: tuple[str, ...]


class EnrichTranscript:
    def __init__(
        self, enricher: Enricher, *, max_summary_words: int = DEFAULT_SUMMARY_WORDS
    ) -> None:
        self._enricher = enricher
        self._max_summary_words = max_summary_words

    async def enrich(self, transcript: CanonicalTranscript) -> EnrichmentResult:
        text = transcript_text(transcript)
        failures: list[str] = []

        chapters: tuple[Chapter, ...] = ()
        try:
            chapters = snap_chapters(await self._enricher.chapters(text), transcript.segments)
        except (TransientError, PermanentError):
            failures.append("chapters")

        summary: str | None = None
        try:
            summary = await self._enricher.summary(text, self._max_summary_words)
        except (TransientError, PermanentError):
            failures.append("summary")

        entities: tuple[str, ...] = ()
        dropped = 0
        try:
            kept, dropped = verify_entities(await self._enricher.entities(text), text)
            entities = tuple(entity.text for entity in kept)
        except (TransientError, PermanentError):
            failures.append("entities")

        return EnrichmentResult(
            chapters=chapters,
            summary=summary,
            entities=entities,
            dropped_entities=dropped,
            failures=tuple(failures),
        )


def transcript_text(transcript: CanonicalTranscript) -> str:
    return " ".join(word.text for segment in transcript.segments for word in segment.words)
