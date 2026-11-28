"""Search the active transcript versions of one tenant (S18, AC-7, AC-8).

The query is normalized the same way as the indexed text (domain.text.normalize, D-057),
embedded with the same model, and sent to the index, which fuses the full-text and vector rankings.
"""

from transcribe_engine.application.ports.search import Embedder, SearchHit, SearchIndex
from transcribe_engine.domain.text import normalize

__all__ = ["SearchTranscripts"]

DEFAULT_LIMIT = 10
MAX_LIMIT = 50


class SearchTranscripts:
    def __init__(self, *, embedder: Embedder, index: SearchIndex) -> None:
        self._embedder = embedder
        self._index = index

    async def __call__(
        self, query: str, *, tenant_id: str, limit: int = DEFAULT_LIMIT
    ) -> tuple[SearchHit, ...]:
        normalized = normalize(query).search.strip()
        if not normalized:
            return ()
        limit = max(1, min(limit, MAX_LIMIT))
        (vector,) = await self._embedder.embed([normalized])
        return await self._index.search(
            tenant_id, self._embedder.model, normalized, list(vector), limit
        )
