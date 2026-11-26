"""In-memory diarizer for the pipeline tests (S17). Returns scripted turns, or raises a chosen
domain error. `calls` counts invocations, which is what the channel-split test asserts (AC-6)."""

from dataclasses import dataclass, field

from transcribe_engine.domain.errors import DomainError
from transcribe_engine.domain.speakers import SpeakerTurn


@dataclass
class FakeDiarizer:
    turns: tuple[SpeakerTurn, ...] = ()
    error: DomainError | None = None
    name: str = "fake-diarizer"
    revision: str = "fake-1"
    max_speakers: int | None = 4
    calls: list[str] = field(default_factory=list)

    async def diarize(self, audio_key: str, num_speakers: int | None) -> tuple[SpeakerTurn, ...]:
        self.calls.append(audio_key)
        if self.error is not None:
            raise self.error
        return self.turns
