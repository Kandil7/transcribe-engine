"""Search ports (S18, design: الـ RAG). The index and the embedder are adapters behind these.

An index keeps embeddings per (tenant, model) and the active version of each transcript. A search
reads only the active version, and only the embeddings of the model that embedded the query.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

__all__ = ["Embedder", "IndexedChunk", "SearchHit", "SearchIndex"]


@dataclass(frozen=True)
class IndexedChunk:
    chunk_id: str
    embedding_id: str
    start_ms: int
    end_ms: int
    body: str
    search_text: str


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    transcript_id: str
    version: int
    media_id: str
    start_ms: int
    end_ms: int
    body: str
    score: float = 0.0


class Embedder(Protocol):
    model: str
    version: str

    def count_tokens(self, text: str) -> int: ...

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class SearchIndex(Protocol):
    async def known_embedding_ids(
        self, tenant_id: str, model: str, embedding_ids: Sequence[str]
    ) -> frozenset[str]: ...

    async def store(  # noqa: PLR0913, PLR0917 - D-079: one argument per stored field
        self,
        tenant_id: str,
        transcript_id: str,
        media_id: str,
        version: int,
        model: str,
        chunks: Sequence[IndexedChunk],
        vectors: Mapping[str, Sequence[float]],
    ) -> None: ...

    async def activate(self, tenant_id: str, transcript_id: str, version: int) -> None: ...

    async def search(
        self,
        tenant_id: str,
        model: str,
        text: str,
        vector: Sequence[float],
        limit: int,
    ) -> tuple[SearchHit, ...]: ...

    async def chunks_of(self, tenant_id: str, transcript_id: str) -> tuple[SearchHit, ...]: ...
