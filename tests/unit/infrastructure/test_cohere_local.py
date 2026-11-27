"""S12 (D-074): the local Cohere ASR adapter turns a chunk into text, then into word times.

The model is a fake runner that returns text, as the real model does (no word timestamps). The
adapter must place that text with the aligner; without an aligner it must refuse rather than
return silence. Positive controls: a silent chunk gives no words and no aligner call, and a normal
chunk gives aligned words. Out-of-memory is transient; other model errors are permanent.
"""

import asyncio
import importlib
import io
import wave
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from tests.fakes.storage import FakeObjectStorage
from tests.fakes.word_aligner import FakeWordAligner
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError, TransientError

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


async def _engine(runner: Any, aligner: Any, samples: np.ndarray) -> Any:
    cohere = _mod("transcribe_engine.infrastructure.asr.cohere_local")
    storage = FakeObjectStorage()
    await storage.put("work/t/j/audio.wav", _wav(samples))
    engine = cohere.CohereLocalASR(storage, runner=runner, aligner=aligner, revision="r")
    return engine, storage


def test_text_is_placed_by_the_aligner() -> None:
    async def run() -> None:
        aligner = FakeWordAligner()
        engine, _ = await _engine(lambda _s: "مرحبا بكم", aligner, np.ones(RATE, dtype=np.int16))
        words = await engine.transcribe("work/t/j/audio.wav", _chunk(), language="ar")
        assert aligner.calls == ["مرحبا بكم"]
        assert [w.text for w in words] == ["مرحبا", "بكم"]

    asyncio.run(run())


def test_silence_gives_no_words_and_no_alignment() -> None:
    async def run() -> None:
        aligner = FakeWordAligner()
        engine, _ = await _engine(lambda _s: "", aligner, np.zeros(RATE, dtype=np.int16))
        assert await engine.transcribe("work/t/j/audio.wav", _chunk(), language="ar") == ()
        assert aligner.calls == []

    asyncio.run(run())


def test_text_without_an_aligner_is_refused() -> None:
    async def run() -> None:
        engine, _ = await _engine(lambda _s: "مرحبا", None, np.ones(RATE, dtype=np.int16))
        with pytest.raises(PermanentError, match="aligner"):
            await engine.transcribe("work/t/j/audio.wav", _chunk(), language="ar")

    asyncio.run(run())


def test_out_of_memory_is_transient_and_other_failures_are_permanent() -> None:
    async def run() -> None:
        def oom(_s: Any) -> str:
            raise RuntimeError("CUDA error: out of memory")

        def broken(_s: Any) -> str:
            raise RuntimeError("unexpected graph state")

        aligner = FakeWordAligner()
        samples = np.ones(RATE, dtype=np.int16)
        engine, _ = await _engine(oom, aligner, samples)
        with pytest.raises(TransientError):
            await engine.transcribe("work/t/j/audio.wav", _chunk(), language="ar")
        engine, _ = await _engine(broken, aligner, samples)
        with pytest.raises(PermanentError):
            await engine.transcribe("work/t/j/audio.wav", _chunk(), language="ar")

    asyncio.run(run())
