"""vLLM ASR (ADR-0007, D-067): text without word times is refused, never an empty transcript.

The production default (Cohere Transcribe Arabic) returns no word timestamps. A chunk with speech
in its text but no word times must fail as permanent, so the job is not completed with silence.
The forced aligner (R-005) is the planned source of word times.

Positive controls: a response with word times returns its words, and a silent chunk (no text, no
words) returns nothing without an error.
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
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError

RATE = 16_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _wav(samples: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(samples.astype("<i2").tobytes())
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


async def _transcribe(body: dict[str, Any]) -> tuple[Any, ...]:
    vllm = _mod("transcribe_engine.infrastructure.asr.vllm_client")
    storage = FakeObjectStorage()
    await storage.put("work/t/j/audio.wav", _wav(np.zeros(RATE, dtype=np.int16)))
    client = vllm.VllmClient(
        "http://vllm.test",
        "model-x",
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=body)),
    )
    return await vllm.VllmASR(storage, client).transcribe(
        "work/t/j/audio.wav", _chunk(), language="ar"
    )


@pytest.mark.xfail(strict=True, reason="S12")
async def test_text_without_word_times_is_refused() -> None:
    with pytest.raises(PermanentError):
        await _transcribe({"text": "مرحبا بكم", "words": []})


async def test_positive_controls_words_and_silence() -> None:
    words = await _transcribe(
        {"text": "مرحبا", "words": [{"word": "مرحبا", "start": 0.0, "end": 0.5}]}
    )
    assert [w.text for w in words] == ["مرحبا"]
    assert await _transcribe({"text": "", "words": []}) == ()
