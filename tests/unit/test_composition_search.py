"""S18 (D-079): search is off by default; the model loads only when the deployment turns it on.

Positive control: with TE_SEARCH_ENABLED off, no embedder is built. The on-path builds the bge-m3
embedder, which needs the cached model; that path is covered by the embedder tests.
"""

from transcribe_engine import main
from transcribe_engine.infrastructure.settings import Settings


def test_search_is_off_by_default() -> None:
    assert Settings().search_enabled is False
    assert main.build_embedder(Settings(search_enabled=False)) is None
