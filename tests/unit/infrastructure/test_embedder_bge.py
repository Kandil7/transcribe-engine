"""S18 (D-079): the bge-m3 embedder returns normalised 1024-dimensional, stable vectors.

Runs the real ONNX model when the pinned snapshot is cached; skipped otherwise, so CI stays green.
Positive controls: 1024 values with unit length, and the same text gives the same vector.
Negative control: a revision that is not in the cache is refused as a permanent error.
"""

import math

import pytest
from huggingface_hub import snapshot_download

from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.infrastructure.search.embedder_bge import (
    BGE_M3_DIMENSIONS,
    BGE_M3_REVISION,
    BgeM3Embedder,
)


def _cached() -> bool:
    try:
        snapshot_download("BAAI/bge-m3", revision=BGE_M3_REVISION, local_files_only=True)
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _cached(), reason="pinned bge-m3 snapshot is not in the local cache")
async def test_vectors_have_1024_unit_values_and_are_deterministic() -> None:
    embedder = BgeM3Embedder()
    first = (await embedder.embed(["مرحبا بكم في الدرس"]))[0]
    again = (await embedder.embed(["مرحبا بكم في الدرس"]))[0]
    assert len(first) == BGE_M3_DIMENSIONS
    assert math.isclose(math.sqrt(sum(x * x for x in first)), 1.0, rel_tol=1e-4)
    assert first == again
    assert embedder.count_tokens("مرحبا بكم") > 0


async def test_a_revision_missing_from_the_cache_is_refused() -> None:
    with pytest.raises(PermanentError, match="not in the local cache"):
        BgeM3Embedder(revision="0" * 40)
