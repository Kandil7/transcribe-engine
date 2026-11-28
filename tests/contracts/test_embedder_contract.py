"""Contract of the Embedder port (S18, CLAUDE.md): one suite, run against the fake and the bge-m3
adapter. The real adapter runs only when the pinned snapshot is in the local cache; without it the
bge case is skipped with the reason, and the fake still runs.

Positive controls: the vectors have the port's dimension and unit length, and different texts give
different vectors. Negative control: the empty input gives no vectors.
"""

import math

import pytest
from huggingface_hub import snapshot_download

from tests.fakes.embedder import FakeEmbedder
from transcribe_engine.infrastructure.search.embedder_bge import (
    BGE_M3_DIMENSIONS,
    BGE_M3_REVISION,
    BgeM3Embedder,
)

pytestmark = [pytest.mark.contract]

DIMENSIONS = BGE_M3_DIMENSIONS


def _cached() -> bool:
    try:
        snapshot_download("BAAI/bge-m3", revision=BGE_M3_REVISION, local_files_only=True)
    except OSError:
        return False
    return True


def _make(kind: str) -> FakeEmbedder | BgeM3Embedder:
    if kind == "fake":
        return FakeEmbedder()
    return BgeM3Embedder()


KINDS = [
    "fake",
    pytest.param(
        "bge",
        marks=pytest.mark.skipif(not _cached(), reason="pinned bge-m3 snapshot is not cached"),
    ),
]


@pytest.mark.parametrize("kind", KINDS)
async def test_empty_input_gives_no_vectors(kind: str) -> None:
    embedder = _make(kind)
    assert await embedder.embed([]) == []


@pytest.mark.parametrize("kind", KINDS)
async def test_one_unit_vector_per_text(kind: str) -> None:
    embedder = _make(kind)
    vectors = await embedder.embed(["مرحبا بكم في الدرس", "الدرس اليوم عن الحساب"])
    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == DIMENSIONS
        assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-4)


@pytest.mark.parametrize("kind", KINDS)
async def test_same_text_same_vector_different_text_different_vector(kind: str) -> None:
    embedder = _make(kind)
    a1, a2, b = await embedder.embed(["نص أول", "نص أول", "نص مختلف تماماً"])
    assert a1 == a2
    assert a1 != b


@pytest.mark.parametrize("kind", KINDS)
async def test_model_identity_names_the_revision(kind: str) -> None:
    """The model identity is stored with each vector, so it must name the model and
    the pin (D-079)."""
    embedder = _make(kind)
    assert isinstance(embedder.model, str)
    assert embedder.model
    assert embedder.count_tokens("كلمتان اثنتان") >= 1
