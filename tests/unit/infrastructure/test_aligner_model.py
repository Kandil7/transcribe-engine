"""S14 (D-070): the real Arabic aligner, when it is in the local cache.

Skipped when the pinned model is not cached, so CI (no model) stays green. When it is cached, the
loader and the adapter run on a short synthetic chunk: the words come back ordered and inside the
chunk. Plausibility only: accuracy is measured later on the reference set (R-001).
"""

import io
import wave

import numpy as np
import pytest

from tests.fakes.storage import FakeObjectStorage
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.infrastructure.alignment.load import load_wav2vec2_aligner

MODEL = "parseh/aligner-ar"
REVISION = "088bb8afed49b11e2a29a7a9b947b479e9ef3eaa"
RATE = 16_000


def _cached() -> bool:
    from huggingface_hub import snapshot_download  # noqa: PLC0415 - optional, as in the loader

    try:
        snapshot_download(MODEL, revision=REVISION, local_files_only=True)
    except OSError:  # not in the cache: the model test is skipped
        return False
    return True


@pytest.mark.skipif(not _cached(), reason="pinned aligner is not in the local cache")
async def test_words_come_back_ordered_and_inside_the_chunk() -> None:
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
    aligner = load_wav2vec2_aligner(storage, MODEL, REVISION)
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
    words = await aligner.align("work/t/j/audio.wav", chunk, "كرة سحرية", language="ar")
    assert [w.text for w in words] == ["كرة", "سحرية"]
    starts = [w.local_start for w in words]
    assert starts == sorted(starts)
    assert all(0 <= w.local_start <= w.local_end <= len(pcm) for w in words)
