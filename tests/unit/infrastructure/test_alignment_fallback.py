"""S14 AC-4 (D-077): an aligner that fails permanently gives segment times, flagged as fallback.

A transient aligner failure is not a fallback: it propagates, so the job retries.
Positive control: a working aligner gives words with fallback off.
"""

import importlib
import io
import wave
from types import ModuleType
from typing import Any

import httpx
import numpy as np
import pytest

from tests.fakes.storage import FakeObjectStorage
from tests.fakes.word_aligner import FakeWordAligner
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError, TransientError

RATE = 16_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(np.zeros(RATE, dtype="<i2").tobytes())
    return buffer.getvalue()


def _chunk() -> Chunk:
    return Chunk(
        chunk_id="c-1",
        job_id="job-1",
        idx=0,
        total=1,
        start_sample=0,
        end_sample=RATE,
        pad_before=0,
        pad_after=0,
        sample_rate=RATE,
        media_sha256="a" * 64,
        config_hash="b" * 64,
    )


class _Raising:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def align(self, audio_key: str, chunk: Any, text: str, *, language: str) -> Any:
        raise self._error


async def _vllm(aligner: Any) -> Any:
    vllm = _mod("transcribe_engine.infrastructure.asr.vllm_client")
    storage = FakeObjectStorage()
    await storage.put("work/t/j/audio.wav", _wav())
    client = vllm.VllmClient(
        "http://vllm.test",
        "model-x",
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"text": "مرحبا بكم", "words": []})
        ),
    )
    return await vllm.VllmASR(storage, client, aligner=aligner).transcribe(
        "work/t/j/audio.wav", _chunk(), language="ar"
    )


async def test_permanent_aligner_failure_falls_back_to_segment_times() -> None:
    words = await _vllm(_Raising(PermanentError("aligner failed")))
    assert [w.text for w in words] == ["مرحبا", "بكم"]
    assert all(w.fallback for w in words)
    assert words[0].local_start == 0
    assert words[-1].local_end == RATE


async def test_transient_aligner_failure_is_not_a_fallback() -> None:
    with pytest.raises(TransientError):
        await _vllm(_Raising(TransientError("aligner busy")))


async def test_working_aligner_gives_words_without_fallback() -> None:
    words = await _vllm(FakeWordAligner())
    assert words
    assert not any(w.fallback for w in words)
