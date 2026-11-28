"""Stub segment aligner for the S22 tests.

It gives each word of the new text a fixed 10 ms slot from the segment start, and records every
segment it was asked to re-align. S22 AC-2 checks that call log.
"""

from dataclasses import dataclass, field

from transcribe_engine.domain.transcript import Word


@dataclass
class FakeAligner:
    calls: list[str] = field(default_factory=list)

    async def realign(
        self,
        tenant_id: str,
        transcript_id: str,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        text: str,
    ) -> tuple[Word, ...]:
        del tenant_id, transcript_id, end_ms
        self.calls.append(segment_id)
        return tuple(
            Word(
                text=word,
                start_ms=start_ms + i * 10,
                end_ms=start_ms + i * 10 + 10,
                lang="ar",
                conf=None,
            )
            for i, word in enumerate(text.split())
        )
