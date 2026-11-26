"""In-memory VAD for unit and integration tests (S10). Returns a configured result."""

from dataclasses import dataclass

from transcribe_engine.application.ports.vad import VadResult


@dataclass
class FakeVad:
    result: VadResult

    async def analyze(self, audio_key: str) -> VadResult:
        return self.result
