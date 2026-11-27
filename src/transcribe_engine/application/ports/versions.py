"""Versioned transcript store and segment aligner ports (S22).

Infrastructure and fakes implement them.

A save writes exactly the next version; the caller has already checked the base version (AC-3).
"""

from collections.abc import Sequence
from typing import Protocol

from transcribe_engine.domain.transcript import CanonicalTranscript, Word

__all__ = ["SegmentAligner", "TranscriptVersions"]


class TranscriptVersions(Protocol):
    async def latest(self, tenant_id: str, transcript_id: str) -> CanonicalTranscript | None: ...

    async def save(self, tenant_id: str, transcript: CanonicalTranscript) -> None:
        """Store `transcript` as its version. The version must be the next one."""
        ...


class SegmentAligner(Protocol):
    async def realign(
        self,
        transcript_id: str,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        text: str,
    ) -> Sequence[Word]:
        """Timed words for `text` inside one segment's span (S14).

        Called for changed segments only."""
        ...
