"""S11 VAD contract (AC-5): the Silero adapter on real audio. Needs the `ml` extra.

Silence gives no regions. Speech-like bursts are found. The fixtures are generated into a temp dir.
Imports happen inside helpers so the module collects before the adapter exists.
"""

import importlib
import io
import math
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


async def test_silence_file_no_regions(tmp_path: Path) -> None:
    _requires_silero()
    assert await _detect(tmp_path, [0] * (5 * RATE)) == ()


async def test_tone_bursts_found(tmp_path: Path) -> None:
    """Two voiced-like bursts (120 Hz harmonics, syllable-rate envelope) at 1-3 s and 5-7 s.

    Silero is trained on speech, so the count on synthetic tones is not a criterion (D-039). The
    contract is: at least one region is reported, and every region lies inside a burst.
    """
    _requires_silero()

    def burst(n: int) -> list[int]:
        out = []
        for i in range(n):
            t = i / RATE
            envelope = 0.5 * (1 - math.cos(2 * math.pi * 4 * t))
            tone = sum(math.sin(2 * math.pi * 120 * k * t) / k for k in range(1, 12))
            out.append(int(9_000 * envelope * tone / 3))
        return out

    samples = [0] * RATE + burst(2 * RATE) + [0] * (2 * RATE) + burst(2 * RATE) + [0] * RATE
    regions = await _detect(tmp_path, samples)
    assert regions
    bursts = [(RATE, 3 * RATE), (5 * RATE, 7 * RATE)]
    for region in regions:
        assert any(
            region.start_sample >= a - RATE // 2 and region.end_sample <= b + RATE // 2
            for a, b in bursts
        ), (region.start_sample, region.end_sample)
