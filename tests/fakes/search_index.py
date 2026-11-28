"""In-memory search index for the S18 tests.

It follows the SearchIndex port's rules, as the Postgres adapter does, so one contract suite
can run against both (tests/contracts).

- A write for a job that is not registered is refused, as the job lock refuses it in Postgres.
- A re-index of a version replaces that version's rows; an embedding no row uses is dropped.
- Activation only moves forward, and the other versions' rows are dropped after it.
- A search reads the active version of each transcript, for one tenant and one model.
- The lexical gate is a match on every query word (D-086); vectors reorder the matches; RRF fuses.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from transcribe_engine.application.errors import TranscriptNotFoundError
from transcribe_engine.application.ports.search import SearchHit
from transcribe_engine.domain.rag import rrf

_CANDIDATES = 50


@dataclass(frozen=True)
class _Row:
    tenant_id: str
    transcript_id: str
    version: int
    media_id: str
    model: str
    chunk_id: str
    embedding_id: str
    start_ms: int
    end_ms: int
    body: str
    search_text: str


@dataclass
class FakeSearchIndex:
    jobs: set[tuple[str, str]] = field(default_factory=set)
    rows: list[_Row] = field(default_factory=list)
    vectors: dict[tuple[str, str], tuple[str, list[float]]] = field(default_factory=dict)
    active: dict[tuple[str, str], int] = field(default_factory=dict)

    def register_job(self, tenant_id: str, job_id: str) -> None:
        self.jobs.add((tenant_id, job_id))

    async def known_embedding_ids(
        self, tenant_id: str, model: str, embedding_ids: Sequence[str]
    ) -> frozenset[str]:
        return frozenset(
            i
            for i in embedding_ids
            if (tenant_id, i) in self.vectors and self.vectors[(tenant_id, i)][0] == model
        )

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
        if (tenant_id, transcript_id) not in self.jobs:
            raise TranscriptNotFoundError
        replaced = {
            r.embedding_id
            for r in self.rows
            if r.tenant_id == tenant_id
            and r.transcript_id == transcript_id
            and r.version == version
        }
        self.rows = [
            r
            for r in self.rows
            if not (
                r.tenant_id == tenant_id
                and r.transcript_id == transcript_id
                and r.version == version
            )
        ]
        for embedding_id, vector in (vectors or {}).items():
            self.vectors.setdefault((tenant_id, embedding_id), (model, list(vector)))
        for chunk in chunks:
            self.rows.append(
                _Row(
                    tenant_id=tenant_id,
                    transcript_id=transcript_id,
                    version=version,
                    media_id=media_id,
                    model=model,
                    chunk_id=chunk.chunk_id,
                    embedding_id=chunk.embedding_id,
                    start_ms=chunk.start_ms,
                    end_ms=chunk.end_ms,
                    body=chunk.body,
                    search_text=chunk.search_text,
                )
            )
        self._purge(tenant_id, replaced)

    async def activate(self, tenant_id: str, transcript_id: str, version: int) -> None:
        if (tenant_id, transcript_id) not in self.jobs:
            raise TranscriptNotFoundError
        current = self.active.get((tenant_id, transcript_id))
        if current is None or current < version:
            self.active[(tenant_id, transcript_id)] = version
        keep = self.active[(tenant_id, transcript_id)]
        dropped = {
            r.embedding_id
            for r in self.rows
            if r.tenant_id == tenant_id and r.transcript_id == transcript_id and r.version != keep
        }
        self.rows = [
            r
            for r in self.rows
            if not (
                r.tenant_id == tenant_id and r.transcript_id == transcript_id and r.version != keep
            )
        ]
        self._purge(tenant_id, dropped)

    async def search(
        self,
        tenant_id: str,
        model: str,
        query: str,
        vector: Sequence[float],
        limit: int,
    ) -> tuple[SearchHit, ...]:
        terms = query.split()
        live = [r for r in self._live(tenant_id) if r.model == model]
        matched = [r for r in live if terms and all(t in r.search_text.split() for t in terms)]
        lexical = sorted(matched, key=lambda r: r.chunk_id)[:_CANDIDATES]
        dense = sorted(
            matched,
            key=lambda r: (
                -_cosine(vector, self.vectors[(tenant_id, r.embedding_id)][1]),
                r.chunk_id,
            ),
        )[:_CANDIDATES]
        by_id = {r.chunk_id: r for r in matched}
        fused = rrf([[r.chunk_id for r in lexical], [r.chunk_id for r in dense]])
        return tuple(
            _hit(by_id[chunk_id], score) for chunk_id, score in fused[:limit] if chunk_id in by_id
        )

    async def chunks_of(self, tenant_id: str, transcript_id: str) -> tuple[SearchHit, ...]:
        rows = [r for r in self._live(tenant_id) if r.transcript_id == transcript_id]
        return tuple(_hit(r, 0.0) for r in sorted(rows, key=lambda r: r.start_ms))

    def _live(self, tenant_id: str) -> list[_Row]:
        return [
            r
            for r in self.rows
            if r.tenant_id == tenant_id
            and self.active.get((r.tenant_id, r.transcript_id)) == r.version
        ]

    def _purge(self, tenant_id: str, candidates: set[str]) -> None:
        used = {r.embedding_id for r in self.rows if r.tenant_id == tenant_id}
        for embedding_id in candidates:
            if embedding_id not in used:
                self.vectors.pop((tenant_id, embedding_id), None)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _hit(row: _Row, score: float) -> SearchHit:
    return SearchHit(
        chunk_id=row.chunk_id,
        transcript_id=row.transcript_id,
        version=row.version,
        media_id=row.media_id,
        start_ms=row.start_ms,
        end_ms=row.end_ms,
        body=row.body,
        score=score,
    )
