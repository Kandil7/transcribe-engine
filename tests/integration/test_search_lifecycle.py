"""S18 lifecycle on Postgres (integration, RLS-enforced role): cases the review found missing.

- Deleting a job removes its searchable text, its active pointer and the embeddings only it used
  (the S21 deletion must reach the RAG tables, D-087).
- A write for a job that was deleted is refused, so an index run cannot bring back its text.
- Searches that run while a new version is being activated each see exactly one version (AC-6, the
  switch is one transaction).

Each check starts from a job whose index rows are actually present (positive control), so a delete
that does nothing cannot pass.
"""

import asyncio
import importlib
import uuid
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.api_support import seed_tenant
from tests.integration.test_deletion import _clock, _make_uow, _seed, _storage
from transcribe_engine.application.errors import TranscriptNotFoundError
from transcribe_engine.infrastructure.db.session import make_engine

pytestmark = [pytest.mark.integration]

VECTOR = [1.0] + [0.0] * 1023
MODEL = "fake-embed@1"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _chunk(chunk_id: str, embedding_id: str, body: str) -> Any:
    ports = _mod("transcribe_engine.application.ports.search")
    return ports.IndexedChunk(
        chunk_id=chunk_id,
        embedding_id=embedding_id,
        start_ms=1_000,
        end_ms=4_000,
        body=body,
        search_text=body,
    )


async def _job(engine: AsyncEngine, storage: Any, tenant: str, job: str) -> None:
    await seed_tenant(engine, tenant)
    await _seed(
        engine,
        storage,
        tenant=tenant,
        job_id=job,
        sha=uuid.uuid4().hex * 2,
        result_key=f"rk-{job}",
    )


async def _count(engine: AsyncEngine, tenant: str, sql: str, **params: Any) -> int:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        return int((await conn.execute(text(sql), {"t": tenant, **params})).scalar_one())


async def test_deleted_job_leaves_no_searchable_text(app_url: str, minio: object) -> None:
    deletion = _mod("transcribe_engine.application.use_cases.delete_job_data")
    search = _mod("transcribe_engine.infrastructure.search.pg_index")
    engine = make_engine(app_url)
    storage = _storage(minio)
    tenant, job = f"tenant-{uuid.uuid4().hex[:8]}", f"job-{uuid.uuid4().hex[:8]}"
    try:
        await _job(engine, storage, tenant, job)
        index = search.SqlSearchIndex(engine)
        await index.store(
            tenant, job, "media", 1, MODEL, [_chunk("c1", "e1", "secretword here")], {"e1": VECTOR}
        )
        await index.activate(tenant, job, 1)

        # Positive control: the text is searchable and its rows exist before the delete.
        assert [
            h.chunk_id for h in await index.search(tenant, MODEL, "secretword", VECTOR, 10)
        ] == ["c1"]
        assert (
            await _count(engine, tenant, "SELECT count(*) FROM rag_chunks WHERE tenant_id = :t")
            == 1
        )

        await deletion.DeleteJobData(_make_uow(engine), storage, _clock())(tenant, job)

        assert await index.search(tenant, MODEL, "secretword", VECTOR, 10) == ()
        assert await index.chunks_of(tenant, job) == ()
        assert (
            await _count(engine, tenant, "SELECT count(*) FROM rag_chunks WHERE tenant_id = :t")
            == 0
        )
        assert (
            await _count(engine, tenant, "SELECT count(*) FROM rag_active WHERE tenant_id = :t")
            == 0
        )
        assert (
            await _count(engine, tenant, "SELECT count(*) FROM rag_embeddings WHERE tenant_id = :t")
            == 0
        )
    finally:
        await engine.dispose()


async def test_write_after_delete_is_refused(app_url: str, minio: object) -> None:
    deletion = _mod("transcribe_engine.application.use_cases.delete_job_data")
    search = _mod("transcribe_engine.infrastructure.search.pg_index")
    engine = make_engine(app_url)
    storage = _storage(minio)
    tenant, job = f"tenant-{uuid.uuid4().hex[:8]}", f"job-{uuid.uuid4().hex[:8]}"
    try:
        await _job(engine, storage, tenant, job)
        index = search.SqlSearchIndex(engine)
        # Positive control: while the job exists, its index write is accepted.
        await index.store(
            tenant, job, "media", 1, MODEL, [_chunk("c1", "e1", "alpha")], {"e1": VECTOR}
        )

        await deletion.DeleteJobData(_make_uow(engine), storage, _clock())(tenant, job)

        with pytest.raises(TranscriptNotFoundError):
            await index.store(
                tenant, job, "media", 2, MODEL, [_chunk("c2", "e2", "alpha")], {"e2": VECTOR}
            )
        with pytest.raises(TranscriptNotFoundError):
            await index.activate(tenant, job, 2)
        assert (
            await _count(engine, tenant, "SELECT count(*) FROM rag_chunks WHERE tenant_id = :t")
            == 0
        )
    finally:
        await engine.dispose()


async def test_searches_during_activation_each_see_one_version(app_url: str, minio: object) -> None:
    """Twenty searches run while version 2 is activated. Each sees exactly one version, and the
    searches after the switch see version 2. Positive control: searches return hits."""
    search = _mod("transcribe_engine.infrastructure.search.pg_index")
    engine = make_engine(app_url)
    storage = _storage(minio)
    tenant, job = f"tenant-{uuid.uuid4().hex[:8]}", f"job-{uuid.uuid4().hex[:8]}"
    try:
        await _job(engine, storage, tenant, job)
        index = search.SqlSearchIndex(engine)
        await index.store(
            tenant, job, "media", 1, MODEL, [_chunk("c1", "e1", "alpha one")], {"e1": VECTOR}
        )
        await index.activate(tenant, job, 1)
        await index.store(
            tenant, job, "media", 2, MODEL, [_chunk("c2", "e2", "alpha two")], {"e2": VECTOR}
        )

        async def search_once() -> set[int]:
            return {h.version for h in await index.search(tenant, MODEL, "alpha", VECTOR, 10)}

        results = await asyncio.gather(
            index.activate(tenant, job, 2), *[search_once() for _ in range(20)]
        )
        seen = results[1:]
        assert any(seen), "the searches return hits (positive control)"
        assert all(len(versions) == 1 for versions in seen), seen
        assert all(versions <= {1, 2} for versions in seen)
        assert {h.version for h in await index.search(tenant, MODEL, "alpha", VECTOR, 10)} == {2}
    finally:
        await engine.dispose()
