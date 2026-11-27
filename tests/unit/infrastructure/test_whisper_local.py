"""Local Whisper adapter (D-063) on a fake storage and a fake pipeline.

The real model is checked by the local smoke test, not here.

Each refusal has a positive control: a word with real times maps to samples, and a normal chunk
produces words, so an adapter that always returns nothing or always fails cannot pass.
"""

import asyncio
import io
import wave
from typing import Any

import numpy as np
import pytest

from tests.fakes.storage import FakeObjectStorage
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.infrastructure.asr import whisper_local
from transcribe_engine.infrastructure.asr.whisper_local import WhisperLocalASR, words_from_output

RATE = 16_000


def _wav(samples: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(samples.astype("<i2").tobytes())
    return buffer.getvalue()


def _chunk(start: int, end: int, pad: int) -> Chunk:
    return Chunk(
        chunk_id="c-1",
        job_id="job-1",
        idx=0,
        total=1,
        start_sample=start,
        end_sample=end,
        pad_before=pad,
        pad_after=pad,
        sample_rate=RATE,
        media_sha256="a" * 64,
        config_hash="b" * 64,
    )


def test_word_times_become_samples() -> None:
    """A word from 0.5 s to 1.25 s is samples 8000 to 20000.

    Positive control: a word with no text is dropped; a word without an end keeps its start.
    """
    output = {
        "chunks": [
            {"text": " مرحبا", "timestamp": (0.5, 1.25)},
            {"text": "   ", "timestamp": (2.0, 2.1)},
            {"text": " بكم", "timestamp": (3.0, None)},
        ]
    }
    words = words_from_output(output, RATE)
    assert [w.text for w in words] == ["مرحبا", "بكم"]
    assert (words[0].local_start, words[0].local_end) == (8_000, 20_000)
    assert words[1].local_end == words[1].local_start == 48_000


def test_chunk_is_transcribed_from_its_padded_window() -> None:
    """The pipeline gets the padded window; the words come back relative to the window start.

    Positive control: the window holds the expected number of samples.
    """
    samples = np.zeros(RATE * 4, dtype=np.int16)
    storage = FakeObjectStorage()
    asyncio.run(storage.put("work/t/j/audio.wav", _wav(samples)))
    calls: list[tuple[int, str]] = []

    def pipeline(inputs: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append((len(inputs["raw"]), str(kwargs["generate_kwargs"]["language"])))
        return {"chunks": [{"text": " مرحبا", "timestamp": (0.5, 1.0)}]}

    adapter = WhisperLocalASR(storage, pipeline=pipeline, revision="test-rev")
    chunk = _chunk(start=RATE, end=2 * RATE, pad=RATE // 2)
    words = asyncio.run(adapter.transcribe("work/t/j/audio.wav", chunk, language="ar"))

    assert calls == [(RATE * 2, "arabic")]  # core of one second plus half a second either side
    assert [(w.text, w.local_start, w.local_end) for w in words] == [("مرحبا", 8_000, 16_000)]


def test_out_of_memory_is_transient_and_other_failures_are_permanent() -> None:
    """An out-of-memory model error can succeed on retry; any other error is permanent.

    Positive control: a clean call returns its words.
    """
    samples = np.zeros(RATE, dtype=np.int16)
    storage = FakeObjectStorage()
    asyncio.run(storage.put("work/t/j/audio.wav", _wav(samples)))
    chunk = _chunk(start=0, end=RATE, pad=0)

    def out_of_memory(inputs: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("CUDA error: out of memory")

    def broken(inputs: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("unexpected graph state")

    def clean(inputs: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {"chunks": [{"text": "نعم", "timestamp": (0.0, 0.4)}]}

    with pytest.raises(TransientError):
        asyncio.run(
            WhisperLocalASR(storage, pipeline=out_of_memory, revision="r").transcribe(
                "work/t/j/audio.wav", chunk, language="ar"
            )
        )
    with pytest.raises(PermanentError):
        asyncio.run(
            WhisperLocalASR(storage, pipeline=broken, revision="r").transcribe(
                "work/t/j/audio.wav", chunk, language="ar"
            )
        )
    assert asyncio.run(
        WhisperLocalASR(storage, pipeline=clean, revision="r").transcribe(
            "work/t/j/audio.wav", chunk, language="ar"
        )
    )


def test_missing_model_is_permanent_not_a_download() -> None:
    """A model not in the local cache is refused with a permanent error; nothing is downloaded.

    Positive control: the revision of a cached snapshot is a commit name, checked by the smoke test.
    """
    with pytest.raises(PermanentError):
        whisper_local._cached_revision("nobody/not-a-real-model-for-tests")
