"""S18 (D-079): search is off by default; the model loads only when the deployment turns it on.

Positive control: with TE_SEARCH_ENABLED off, no embedder is built. The on-path builds the bge-m3
embedder, which needs the cached model; that path is covered by the embedder tests.
"""

import pytest

from transcribe_engine import main
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.infrastructure.settings import Settings


def test_search_is_off_by_default() -> None:
    assert Settings().search_enabled is False
    assert main.build_embedder(Settings(search_enabled=False)) is None


def test_search_on_builds_the_bge_embedder() -> None:
    """With TE_SEARCH_ENABLED the composition root builds the embedder. Construction reads the model
    tokenizer from the local cache, so the check runs only where the pinned snapshot is cached."""
    from transcribe_engine.infrastructure.search.embedder_bge import BgeM3Embedder  # noqa: PLC0415

    try:
        built = main.build_embedder(Settings(search_enabled=True))
    except PermanentError as exc:  # the cache is missing: the adapter refuses with this
        pytest.skip(f"bge-m3 snapshot is not cached: {exc}")
    assert isinstance(built, BgeM3Embedder)
