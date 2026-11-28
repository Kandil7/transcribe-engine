"""Postgres search index (S18, D-057, D-079): full-text and vector search, fused by reciprocal rank.

- Embeddings are stored once per (tenant, embedding_id). A chunk row points at its embedding.
- A search reads only the active version of each transcript (rag_active), so a re-index is invisible
  until it is activated (AC-6). Tenant isolation is the RLS policy plus the tenant filter (AC-7).
- Full-text search uses Postgres' built-in ranking on normalized text (D-057; not true BM25).
- Vector search uses the pgvector cosine distance. The two rankings are fused by domain.rag.rrf.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from transcribe_engine.application.errors import TranscriptNotFoundError
from transcribe_engine.application.ports.search import IndexedChunk, SearchHit
from transcribe_engine.domain.rag import rrf

__all__ = ["SqlSearchIndex"]

_CANDIDATES = 50  # candidates per ranking before fusion

_ACTIVE_CHUNK_COLUMNS = (
    "c.chunk_id, c.transcript_id, c.transcript_version, c.media_id, c.start_ms, c.end_ms, c.body"
)
_ACTIVE_JOIN = (
    "FROM rag_chunks c JOIN rag_active a ON a.tenant_id = c.tenant_id "
    "AND a.transcript_id = c.transcript_id AND a.transcript_version = c.transcript_version"
)


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


async def _set_tenant(conn: AsyncConnection, tenant_id: str) -> None:
    await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})


async def _lock_job(conn: AsyncConnection, tenant_id: str, job_id: str) -> None:
    """Hold the job row for share until this transaction ends (D-087).

    A delete of the job waits for this transaction, and a job already deleted is refused here. So an
    index write can never be left behind after its job is deleted, whichever order they run in."""
    locked = (
        await conn.execute(
            text("SELECT id FROM jobs WHERE id = :j AND tenant_id = :t FOR SHARE"),
            {"j": job_id, "t": tenant_id},
        )
    ).first()
    if locked is None:
        raise TranscriptNotFoundError


def _hit(row: Row[Any]) -> SearchHit:
    return SearchHit(
        chunk_id=row.chunk_id,
        transcript_id=row.transcript_id,
        version=int(row.transcript_version),
        media_id=row.media_id,
        start_ms=int(row.start_ms),
        end_ms=int(row.end_ms),
        body=row.body,
    )


class SqlSearchIndex:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def known_embedding_ids(
        self, tenant_id: str, model: str, embedding_ids: Sequence[str]
    ) -> frozenset[str]:
        if not embedding_ids:
            return frozenset()
        async with self._engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            result = await conn.execute(
                text(
                    "SELECT embedding_id FROM rag_embeddings "
                    "WHERE tenant_id = :t AND embedding_model = :m AND embedding_id = ANY(:ids)"
                ),
                {"t": tenant_id, "m": model, "ids": list(embedding_ids)},
            )
            return frozenset(result.scalars())

    async def store(  # noqa: PLR0913, PLR0917 - D-079: one argument per stored field
        self,
        tenant_id: str,
        transcript_id: str,
        media_id: str,
        version: int,
        model: str,
        chunks: Sequence[IndexedChunk],
        vectors: Mapping[str, Sequence[float]],
    ) -> None:
        async with self._engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            await _lock_job(conn, tenant_id, transcript_id)
            # A re-index of this version replaces its rows in this transaction: no duplicates, and
            # no chunk left from an earlier run (review finding: config or text changes).
            replaced = (
                (
                    await conn.execute(
                        text(
                            "DELETE FROM rag_chunks WHERE tenant_id = :t AND transcript_id = :tr "
                            "AND transcript_version = :v RETURNING embedding_id"
                        ),
                        {"t": tenant_id, "tr": transcript_id, "v": version},
                    )
                )
                .scalars()
                .all()
            )
            for embedding_id, vector in vectors.items():
                await conn.execute(
                    text(
                        "INSERT INTO rag_embeddings "
                        "(tenant_id, embedding_id, embedding_model, vector) "
                        "VALUES (:t, :e, :m, CAST(:v AS vector)) "
                        "ON CONFLICT (tenant_id, embedding_id) DO NOTHING"
                    ),
                    {
                        "t": tenant_id,
                        "e": embedding_id,
                        "m": model,
                        "v": _vector_literal(vector),
                    },
                )
            for chunk in chunks:
                await conn.execute(
                    text(
                        "INSERT INTO rag_chunks (tenant_id, chunk_id, transcript_id, "
                        "transcript_version, media_id, start_ms, end_ms, body, search_text, "
                        "embedding_id, embedding_model) "
                        "VALUES (:t, :c, :tr, :v, :md, :s, :en, :b, :st, :e, :m) "
                        "ON CONFLICT (tenant_id, chunk_id) DO UPDATE SET body = EXCLUDED.body, "
                        "search_text = EXCLUDED.search_text, embedding_id = EXCLUDED.embedding_id"
                    ),
                    {
                        "t": tenant_id,
                        "c": chunk.chunk_id,
                        "tr": transcript_id,
                        "v": version,
                        "md": media_id,
                        "s": chunk.start_ms,
                        "en": chunk.end_ms,
                        "b": chunk.body,
                        "st": chunk.search_text,
                        "e": chunk.embedding_id,
                        "m": model,
                    },
                )
            # Embeddings the replaced rows used and the new rows do not: purged after the inserts,
            # so an embedding the new rows reuse is kept (the sweep checks for references).
            await purge_unused_embeddings(conn, tenant_id, sorted(set(replaced)))

    async def activate(self, tenant_id: str, transcript_id: str, version: int) -> None:
        """Make `version` the active one, only if it is newer (D-087).

        Activation is monotonic: a slow index of an older version cannot replace a newer one. After
        it, the chunks of the other versions are removed, and so are the embeddings nothing uses."""
        async with self._engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            await _lock_job(conn, tenant_id, transcript_id)
            await conn.execute(
                text(
                    "INSERT INTO rag_active (tenant_id, transcript_id, transcript_version) "
                    "VALUES (:t, :tr, :v) "
                    "ON CONFLICT (tenant_id, transcript_id) DO UPDATE "
                    "SET transcript_version = EXCLUDED.transcript_version "
                    "WHERE rag_active.transcript_version < EXCLUDED.transcript_version"
                ),
                {"t": tenant_id, "tr": transcript_id, "v": version},
            )
            active = (
                await conn.execute(
                    text(
                        "SELECT transcript_version FROM rag_active "
                        "WHERE tenant_id = :t AND transcript_id = :tr"
                    ),
                    {"t": tenant_id, "tr": transcript_id},
                )
            ).scalar_one()
            dropped = (
                (
                    await conn.execute(
                        text(
                            "DELETE FROM rag_chunks WHERE tenant_id = :t AND transcript_id = :tr "
                            "AND transcript_version <> :v RETURNING embedding_id"
                        ),
                        {"t": tenant_id, "tr": transcript_id, "v": int(active)},
                    )
                )
                .scalars()
                .all()
            )
            await purge_unused_embeddings(conn, tenant_id, list(dropped))

    async def search(
        self,
        tenant_id: str,
        model: str,
        query: str,
        vector: Sequence[float],
        limit: int,
    ) -> tuple[SearchHit, ...]:
        async with self._engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            lexical = (
                await conn.execute(
                    text(
                        f"SELECT {_ACTIVE_CHUNK_COLUMNS} {_ACTIVE_JOIN} "
                        "WHERE c.tenant_id = :t AND c.embedding_model = :m "
                        "AND to_tsvector('simple', c.search_text) @@ plainto_tsquery('simple', :q) "
                        "ORDER BY ts_rank(to_tsvector('simple', c.search_text), "
                        "plainto_tsquery('simple', :q)) DESC, c.chunk_id LIMIT :k"
                    ),
                    {"t": tenant_id, "m": model, "q": query, "k": _CANDIDATES},
                )
            ).all()
            # D-086: a hit must match the query's words. Vectors only reorder those matches, so a
            # query with no matching word returns nothing, whatever the nearest neighbours are.
            matched = [row.chunk_id for row in lexical]
            dense = (
                (
                    await conn.execute(
                        text(
                            f"SELECT {_ACTIVE_CHUNK_COLUMNS} {_ACTIVE_JOIN} "
                            "JOIN rag_embeddings e ON e.tenant_id = c.tenant_id "
                            "AND e.embedding_id = c.embedding_id "
                            "WHERE c.tenant_id = :t AND c.embedding_model = :m "
                            "AND c.chunk_id = ANY(:ids) "
                            "ORDER BY e.vector <=> CAST(:v AS vector), c.chunk_id LIMIT :k"
                        ),
                        {
                            "t": tenant_id,
                            "m": model,
                            "ids": matched,
                            "v": _vector_literal(vector),
                            "k": _CANDIDATES,
                        },
                    )
                ).all()
                if matched
                else []
            )
        by_id: dict[str, SearchHit] = {}
        for row in [*lexical, *dense]:
            by_id.setdefault(row.chunk_id, _hit(row))
        fused = rrf([matched, [row.chunk_id for row in dense]])
        return tuple(replace(by_id[chunk_id], score=score) for chunk_id, score in fused[:limit])

    async def chunks_of(self, tenant_id: str, transcript_id: str) -> tuple[SearchHit, ...]:
        async with self._engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            rows = (
                await conn.execute(
                    text(
                        f"SELECT {_ACTIVE_CHUNK_COLUMNS} {_ACTIVE_JOIN} "
                        "WHERE c.tenant_id = :t AND c.transcript_id = :tr ORDER BY c.start_ms"
                    ),
                    {"t": tenant_id, "tr": transcript_id},
                )
            ).all()
        return tuple(_hit(row) for row in rows)


async def purge_unused_embeddings(conn: AsyncConnection, tenant_id: str, ids: list[str]) -> int:
    """Delete the given embeddings of one tenant that no chunk refers to any more (D-087).

    Only the ids passed in are candidates, so the sweep costs the size of the change, not the index.
    Run after the chunks that held the ids have been deleted in an earlier statement."""
    if not ids:
        return 0
    result = await conn.execute(
        text(
            "DELETE FROM rag_embeddings e WHERE e.tenant_id = :t AND e.embedding_id = ANY(:ids) "
            "AND NOT EXISTS (SELECT 1 FROM rag_chunks c WHERE c.tenant_id = e.tenant_id "
            "AND c.embedding_id = e.embedding_id)"
        ),
        {"t": tenant_id, "ids": ids},
    )
    return int(result.rowcount)
