"""S14 (D-070): the Arabic wav2vec2 aligner turns model frames into word times in samples.

The ONNX session is a fake that emits known frames, so the mapping from frames to words is tested
without the model. Positive control: "a b" with frames for a, a, |, b, b gives two words at the
frame offsets of their characters. A silent chunk with no text gives no words.
"""

import importlib
import io
import wave
from types import ModuleType
from typing import Any

import numpy as np

from tests.fakes.storage import FakeObjectStorage
from transcribe_engine.domain.chunks import Chunk

RATE = 16_000
VOCAB = {"<pad>": 0, "|": 1, "a": 2, "b": 3}
STRIDE = 320  # wav2vec2 emits one frame per 20 ms at 16 kHz


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


class _Input:
    name = "input_values"


class _Session:
    """Emits one logit row per frame: the given symbol id is high, the rest low."""

    def __init__(self, emitted: list[int]) -> None:
        self._emitted = emitted

    def get_inputs(self) -> list[_Input]:
        return [_Input()]

    def run(self, _outputs: Any, feed: dict[str, np.ndarray]) -> list[np.ndarray]:
        assert feed["input_values"].ndim == 2
        logits = np.full((1, len(self._emitted), len(VOCAB)), -10.0, dtype=np.float32)
        for t, symbol in enumerate(self._emitted):
            logits[0, t, symbol] = 10.0
        return [logits]


def _wav(samples: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(samples.astype("<i2").tobytes())
    return buffer.getvalue()


def _chunk(seconds: float) -> Chunk:
    end = int(seconds * RATE)
    return Chunk(
        chunk_id="c-1",
        job_id="job-1",
        idx=0,
        total=1,
        start_sample=0,
        end_sample=end,
        pad_before=0,
        pad_after=0,
        sample_rate=RATE,
        media_sha256="a" * 64,
        config_hash="b" * 64,
    )


async def _align(emitted: list[int], text: str, seconds: float) -> tuple[Any, ...]:
    aligner = _mod("transcribe_engine.infrastructure.alignment.wav2vec2_aligner")
    storage = FakeObjectStorage()
    await storage.put("work/t/j/audio.wav", _wav(np.zeros(int(seconds * RATE), dtype=np.int16)))
    adapter = aligner.Wav2Vec2Aligner(storage, _Session(emitted), VOCAB, blank=0)
    return await adapter.align("work/t/j/audio.wav", _chunk(seconds), text, language="ar")


async def test_words_are_placed_at_their_frames() -> None:
    # frames: pad, a, a, |, |, b, b, pad  -> "a" covers frames 1-2, "b" covers frames 5-6
    emitted = [0, 2, 2, 1, 1, 3, 3, 0]
    words = await _align(emitted, "a b", seconds=len(emitted) * STRIDE / RATE)
    assert [(w.text, w.local_start, w.local_end) for w in words] == [
        ("a", 1 * STRIDE, 3 * STRIDE),
        ("b", 5 * STRIDE, 7 * STRIDE),
    ]


async def test_silent_chunk_without_text_has_no_words() -> None:
    assert await _align([0, 0, 0, 0], "", seconds=4 * STRIDE / RATE) == ()
