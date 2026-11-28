"""S22 (R-005, D-070): a correction that changes a segment is re-aligned with the real aligner.

The segment's audio is cut from the job's normalized file, the corrected text is placed on the
frames (the same forced alignment as the chunks), and the word times come back in absolute
milliseconds inside the segment.

Positive control: the words land at their frames, offset by the segment start. Negative controls:
a failing model, and a job whose audio is gone, both refuse with AlignmentUnavailableError (503),
never with invented times.
"""

import importlib
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from tests.fakes.storage import FakeObjectStorage
from tests.unit.infrastructure.test_wav2vec2_aligner import (
    RATE,
    STRIDE,
    VOCAB,
    _Session,
    _wav,
)

TENANT = "tenant-s22"
JOB = "job-s22"
AUDIO_KEY = f"work/{TENANT}/{JOB}/audio.wav"
SEGMENT_START_MS = 2_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


class _Boom:
    """A session whose run fails, as onnxruntime does when a batch cannot run."""

    def get_inputs(self) -> list[Any]:
        class _Input:
            name = "input_values"

        return [_Input()]

    def run(self, _outputs: Any, _feed: Any) -> Any:
        raise RuntimeError("model failed")


async def _realigner(session: Any, *, with_audio: bool, seconds: float) -> Any:
    aligner = _mod("transcribe_engine.infrastructure.alignment.wav2vec2_aligner")
    storage = FakeObjectStorage()
    if with_audio:
        await storage.put(AUDIO_KEY, _wav(np.zeros(int(seconds * RATE), dtype=np.int16)))
    segment_aligner = aligner.Wav2Vec2Aligner(storage, session, VOCAB, blank=0)
    realign = _mod("transcribe_engine.infrastructure.alignment.segment_realigner")
    return realign.SegmentRealigner(storage, segment_aligner, language="ar")


async def test_words_land_at_their_frames_inside_the_segment() -> None:
    """Frames: pad, a, a, |, |, b, b, pad. "a" covers frames 1-2 and "b" frames 5-6. The
    segment starts at 2 000 ms, so "a" is at 2 020 to 2 060 ms, and "b" at 2 100 to 2 140 ms."""
    emitted = [0, 2, 2, 1, 1, 3, 3, 0]
    seconds = SEGMENT_START_MS / 1000 + len(emitted) * STRIDE / RATE
    realigner = await _realigner(_Session(emitted), with_audio=True, seconds=seconds)
    end_ms = SEGMENT_START_MS + len(emitted) * 20
    words = await realigner.realign(TENANT, JOB, "seg-1", SEGMENT_START_MS, end_ms, "a b")
    assert [(w.text, w.start_ms, w.end_ms) for w in words] == [
        ("a", 2_020, 2_060),
        ("b", 2_100, 2_140),
    ]


async def test_a_failing_model_is_unavailable_not_invented_times() -> None:
    from transcribe_engine.application.errors import AlignmentUnavailableError  # noqa: PLC0415

    realigner = await _realigner(_Boom(), with_audio=True, seconds=3.0)
    with pytest.raises(AlignmentUnavailableError):
        await realigner.realign(TENANT, JOB, "seg-1", 0, 1_000, "a b")


async def test_missing_audio_is_unavailable() -> None:
    from transcribe_engine.application.errors import AlignmentUnavailableError  # noqa: PLC0415

    realigner = await _realigner(_Session([0, 2, 0]), with_audio=False, seconds=1.0)
    with pytest.raises(AlignmentUnavailableError):
        await realigner.realign(TENANT, JOB, "seg-1", 0, 1_000, "a")
