"""Fake word aligner for the S14 tests.

Returns one word per whitespace-separated token, evenly spaced."""

from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.merge import RawWord


class FakeWordAligner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def align(
        self, audio_key: str, chunk: Chunk, text: str, *, language: str
    ) -> tuple[RawWord, ...]:
        self.calls.append(text)
        tokens = text.split()
        span = max(1, chunk.end_sample - chunk.start_sample) // max(1, len(tokens))
        return tuple(
            RawWord(
                text=token,
                local_start=i * span,
                local_end=(i + 1) * span,
                conf=None,
            )
            for i, token in enumerate(tokens)
        )
