"""S12 (D-074): the real local Cohere model, when it is cached at the pinned revision.

Skipped when the model is not cached, so CI (no model) stays green. When it is cached, the engine
loads the model offline, transcribes a short synthetic chunk, and hands any text to the aligner.
Plausibility only: accuracy is unmeasured (D-075).
"""

import io
import wave

import numpy as np
import pytest

from tests.fakes.storage import FakeObjectStorage
from tests.fakes.word_aligner import FakeWordAligner
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.infrastructure.asr.cohere_local import (
    DEFAULT_MODEL_ID,
    DEFAULT_REVISION,
    CohereLocalASR,
)

RATE = 16_000


def _cached() -> bool:
    from huggingface_hub import snapshot_download  # noqa: PLC0415 - optional, as in the loader

    try:
        snapshot_download(DEFAULT_MODEL_ID, revision=DEFAULT_REVISION, local_files_only=True)
    except OSError:  # not in the cache, or the repo is not complete: skip
        return False
    return True


@pytest.mark.skipif(not _cached(), reason="pinned Cohere model is not in the local cache")
async def test_loads_offline_and_hands_text_to_the_aligner() -> None:
    seconds = 2
    rng = np.random.default_rng(0)
    pcm = (rng.standard_normal(seconds * RATE) * 800).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(pcm.tobytes())
    storage = FakeObjectStorage()
    await storage.put("work/t/j/audio.wav", buffer.getvalue())
    aligner = FakeWordAligner()
    engine = CohereLocalASR(storage, device="cuda", aligner=aligner)
    engine.load()
    chunk = Chunk(
        chunk_id="c",
        job_id="j",
        idx=0,
        total=1,
        start_sample=0,
        end_sample=len(pcm),
        pad_before=0,
        pad_after=0,
        sample_rate=RATE,
        media_sha256="a" * 64,
        config_hash="b" * 64,
    )
    words = await engine.transcribe("work/t/j/audio.wav", chunk, language="ar")
    assert isinstance(words, tuple)
    assert all(0 <= w.local_start <= w.local_end <= len(pcm) for w in words)
    assert len(aligner.calls) <= 1  # the aligner is asked once, and only when there is text
