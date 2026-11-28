"""S18 (D-079): the bge-m3 embedder refuses a revision that is not in the local cache.

The vector checks (1024 unit values, the same text giving the same vector) load the 2.2 GB model, so
they run in the contract suite (tests/contracts/test_embedder_contract.py, `make itest`), not in the
unit gate. Negative control: a missing revision is a permanent error, without loading any weights.
"""

import pytest

from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.infrastructure.search.embedder_bge import BgeM3Embedder


async def test_a_revision_missing_from_the_cache_is_refused() -> None:
    with pytest.raises(PermanentError, match="not in the local cache"):
        BgeM3Embedder(revision="0" * 40)
