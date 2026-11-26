"""Diarizer port (S17). The adapters (pyannote, Sortformer) and the fake implement it.

A diarizer runs once on the whole file, so speaker ids are stable across chunks (design: 6).
"""

from collections.abc import Sequence
from typing import Protocol

from transcribe_engine.domain.speakers import SpeakerTurn

__all__ = ["Diarizer"]


class Diarizer(Protocol):
    name: str
    revision: str
    max_speakers: int | None  # None means no limit (design: 6, Sortformer publishes 4)

    async def diarize(self, audio_key: str, num_speakers: int | None) -> Sequence[SpeakerTurn]:
        """Speaker turns for the whole file. Raises TransientError or PermanentError on failure."""
        ...
