"""S18 AC-6 and AC-7 (integration, Postgres): searches see one version at a time, and never
another tenant's data.

AC-6: while version 2 is stored but not active, a search returns only version 1; after
activation, only version 2. AC-7: a second tenant's search returns nothing for the first
tenant's text.
Positive controls: each search finds its own tenant's active text.
"""

import importlib
from types import ModuleType

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.api_support import seed_tenant

pytestmark = [pytest.mark.integration]

VECTOR = [1.0] + [0.0] * 1023


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _chunk(chunk_id: str, embedding_id: str, body: str) -> object:
    ports = _mod("transcribe_engine.application.ports.search")
    return ports.IndexedChunk(
        chunk_id=chunk_id,
        embedding_id=embedding_id,
        start_ms=1_000,
        end_ms=4_000,
        body=body,
        search_text=body,
    )


@pytest.mark.xfail(strict=True, reason="S18")
async def test_atomic_version_switch(pg_url: str) -> None:
    index_mod = _mod("transcribe_engine.infrastructure.search.pg_index")
    engine = create_async_engine(pg_url)
    try:
        await seed_tenant(engine, "tenant-s18-a")
        index = index_mod.SqlSearchIndex(engine)
        await index.store(
            "tenant-s18-a",
            "job-s18-v",
            "media-s18",
            1,
            "fake-embed",
            [_chunk("ch-v1", "em-v1", "alpha beta")],
            {"em-v1": VECTOR},
        )
        await index.activate("tenant-s18-a", "job-s18-v", 1)
        before = await index.search("tenant-s18-a", "fake-embed", "alpha", VECTOR, 10)
        assert [h.chunk_id for h in before] == ["ch-v1"]

        await index.store(
            "tenant-s18-a",
            "job-s18-v",
            "media-s18",
            2,
            "fake-embed",
            [_chunk("ch-v2", "em-v2", "alpha gamma")],
            {"em-v2": VECTOR},
        )
        during = await index.search("tenant-s18-a", "fake-embed", "alpha", VECTOR, 10)
        assert {h.version for h in during} == {1}

        await index.activate("tenant-s18-a", "job-s18-v", 2)
        after = await index.search("tenant-s18-a", "fake-embed", "alpha", VECTOR, 10)
        assert {h.version for h in after} == {2}
    finally:
        await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S18")
async def test_tenant_isolation(pg_url: str) -> None:
    index_mod = _mod("transcribe_engine.infrastructure.search.pg_index")
    engine = create_async_engine(pg_url)
    try:
        await seed_tenant(engine, "tenant-s18-b")
        await seed_tenant(engine, "tenant-s18-c")
        index = index_mod.SqlSearchIndex(engine)
        await index.store(
            "tenant-s18-b",
            "job-s18-iso",
            "media-s18",
            1,
            "fake-embed",
            [_chunk("ch-iso", "em-iso", "secret phrase")],
            {"em-iso": VECTOR},
        )
        await index.activate("tenant-s18-b", "job-s18-iso", 1)
        own = await index.search("tenant-s18-b", "fake-embed", "secret", VECTOR, 10)
        assert [h.chunk_id for h in own] == ["ch-iso"]
        other = await index.search("tenant-s18-c", "fake-embed", "secret", VECTOR, 10)
        assert other == []
    finally:
        await engine.dispose()
