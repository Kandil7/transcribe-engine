"""The aligner used when no real one is configured (S22, R-005).

It refuses instead of inventing word times. A correction that needs new timings is therefore not
saved until an aligner is configured. Corrections that change no timing still work.
"""

from collections.abc import Sequence

from transcribe_engine.application.errors import AlignmentUnavailableError
from transcribe_engine.domain.transcript import Word

__all__ = ["UnavailableAligner"]


class UnavailableAligner:
    async def realign(
        self,
        tenant_id: str,
        transcript_id: str,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        text: str,
    ) -> Sequence[Word]:
        del transcript_id, segment_id, start_ms, end_ms, text
        raise AlignmentUnavailableError
