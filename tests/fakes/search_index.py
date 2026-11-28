"""In-memory search index for the S18 unit tests.

It keeps embeddings by (tenant, model) and the active version of each transcript. The SQL index is
tested separately, against Postgres."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeSearchIndex:
    embeddings: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    rows: list[Any] = field(default_factory=list)
    active: dict[tuple[str, str], int] = field(default_factory=dict)

    async def known_embedding_ids(
        self, tenant_id: str, model: str, embedding_ids: Sequence[str]
    ) -> frozenset[str]:
        known = self.embeddings.get((tenant_id, model), set())
        return frozenset(i for i in embedding_ids if i in known)

    async def store(  # noqa: PLR0917 - mirrors the SearchIndex port's signature
        self,
        tenant_id: str,
        transcript_id: str,
        media_id: str,
        version: int,
        model: str,
        chunks: Sequence[Any],
        vectors: Mapping[str, Sequence[float]] | None = None,
    ) -> None:
        vectors = vectors or {}
        self.embeddings.setdefault((tenant_id, model), set()).update(vectors)
        self.rows.append((tenant_id, transcript_id, version, [c.chunk_id for c in chunks]))

    async def activate(self, tenant_id: str, transcript_id: str, version: int) -> None:
        self.active[(tenant_id, transcript_id)] = version
