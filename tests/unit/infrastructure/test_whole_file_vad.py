"""Plumbing VAD reads the sample count from the WAV header without downloading the file (S10).

Positive control: a valid 16 kHz mono WAV reports its exact sample count with one region. The
refusals are paired with it so an always-refusing adapter cannot pass.
"""

import importlib
import io
import wave
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _wav(samples: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\x00\x00" * samples)
    return buffer.getvalue()


async def _vad(data: bytes) -> object:
    fakes_storage = _mod("tests.fakes.storage")
    storage = fakes_storage.FakeObjectStorage()
    await storage.put("work/t/j/audio.wav", data)
    vad = _mod("transcribe_engine.infrastructure.vad.whole_file").WholeFileVad(storage)
    return await vad.analyze("work/t/j/audio.wav")


async def test_valid_wav_reports_its_sample_count_and_one_region() -> None:
    result = await _vad(_wav(16_000))
    assert result.total_samples == 16_000
    assert [(r.start_sample, r.end_sample) for r in result.regions] == [(0, 16_000)]


async def test_truncated_data_chunk_is_clipped_to_the_bytes_present() -> None:
    data = _wav(16_000)
    result = await _vad(data[: len(data) // 2])
    assert result.total_samples == (len(data) // 2 - 44) // 2


async def test_non_wav_is_refused() -> None:
    domain_errors = _mod("transcribe_engine.domain.errors")
    with pytest.raises(domain_errors.PermanentError):
        await _vad(b"#EXTM3U\n" + b"x" * 100)
