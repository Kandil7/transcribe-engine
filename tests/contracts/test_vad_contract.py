"""S11 VAD contract (AC-5): the Silero adapter on real audio. Needs the `ml` extra.

Silence gives no regions. Speech-like bursts are found. The fixtures are generated into a temp dir.
Imports happen inside helpers so the module collects before the adapter exists.
"""

import importlib
import io
import random
import wave
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.contract
RATE = 16_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _requires_silero() -> None:
    pytest.importorskip("silero_vad")
    pytest.importorskip("torch")


def _wav_bytes(samples: list[int]) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b"".join(s.to_bytes(2, "little", signed=True) for s in samples))
    return buffer.getvalue()


async def _detect(tmp_path: Path, samples: list[int]) -> tuple[object, ...]:
    storage = _mod("tests.fakes.storage").FakeObjectStorage()
    await storage.put("work/t/j/audio.wav", _wav_bytes(samples))
    detector = _mod("transcribe_engine.infrastructure.ml.silero_vad").SileroVad(
        storage=storage, scratch=tmp_path
    )
    params = _mod("transcribe_engine.domain.vad").VadParams(
        threshold=0.5, min_silence_ms=500, min_speech_ms=250
    )
    return tuple(await detector.detect("work/t/j/audio.wav", params))


@pytest.mark.xfail(strict=True, reason="S11")
async def test_silence_file_no_regions(tmp_path: Path) -> None:
    _requires_silero()
    assert await _detect(tmp_path, [0] * (5 * RATE)) == ()


@pytest.mark.xfail(strict=True, reason="S11")
async def test_tone_bursts_found(tmp_path: Path) -> None:
    """Two bursts of speech-band noise separated by 2 s of silence are both reported."""
    _requires_silero()
    rng = random.Random(7)
    burst = [int(rng.uniform(-12_000, 12_000)) for _ in range(2 * RATE)]
    samples = [0] * RATE + burst + [0] * (2 * RATE) + burst + [0] * RATE
    regions = await _detect(tmp_path, samples)
    assert len(regions) >= 2
