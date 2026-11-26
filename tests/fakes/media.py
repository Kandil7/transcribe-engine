"""In-memory media probe and normalizer for unit tests (S09). Each records its calls.

The fakes do not decode anything. Tests configure the facts they need: the probe result or a
refusal, and the normalizer's output or refusal.
"""

from dataclasses import dataclass, field
from pathlib import Path

from transcribe_engine.application.ports.media import MediaInfo, NormalizedAudio


@dataclass
class FakeMediaProbe:
    info: MediaInfo | None = None
    error: Exception | None = None
    calls: list[Path] = field(default_factory=list)

    async def probe(self, path: Path) -> MediaInfo:
        self.calls.append(path)
        if self.error is not None:
            raise self.error
        if self.info is None:
            raise AssertionError("FakeMediaProbe has no info configured")
        return self.info


@dataclass
class FakeAudioNormalizer:
    output: NormalizedAudio | None = None
    error: Exception | None = None
    payload: bytes = b"RIFF-fake-wav"
    calls: list[tuple[Path, Path]] = field(default_factory=list)

    async def to_pcm16_mono_16k(self, src: Path, dst: Path, *, timeout_s: float) -> NormalizedAudio:
        self.calls.append((src, dst))
        if self.error is not None:
            raise self.error
        if self.output is None:
            raise AssertionError("FakeAudioNormalizer has no output configured")
        dst.write_bytes(self.payload)
        return self.output
