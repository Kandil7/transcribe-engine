"""VAD port (S10, minimal; real adapters arrive in S11). Finds speech regions in normalized audio.

The port reports the total length in samples too, so the planner can pad chunks inside the file.
The parameters come from the job's pipeline config (S11).
"""

from dataclasses import dataclass
from typing import Protocol

from transcribe_engine.domain.chunks import SpeechRegion
from transcribe_engine.domain.vad import VadParams

__all__ = ["VadResult", "VoiceActivity"]


@dataclass(frozen=True)
class VadResult:
    total_samples: int
    regions: tuple[SpeechRegion, ...]


class VoiceActivity(Protocol):
    async def analyze(self, audio_key: str, params: VadParams) -> VadResult: ...
