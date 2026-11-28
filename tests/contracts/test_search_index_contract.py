"""Contract of the SearchIndex port (S18, CLAUDE.md): one suite, run against the fake and the
Postgres adapter. A fake that disagrees with the adapter is a bug in the fake, so both must pass
the same rules.

Every scenario has a positive control (the thing it checks is actually found first), so an index
that returns nothing cannot pass. The Postgres run uses the RLS-enforced role (app_url), so the
tenant checks test the policy, not only the SQL filter.
"""

import contextlib
import importlib
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes.search_index import FakeSearchIndex

pytestmark = [pytest.mark.contract]

MODEL = "fake-embed@1"
VECTOR = [1.0] + [0.0] * 1023


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _chunk(chunk_id: str, embedding_id: str, body: str, start_ms: int = 1_000) -> Any:
    ports = _mod("transcribe_engine.application.ports.search")
    return ports.IndexedChunk(
        chunk_id=chunk_id,
        embedding_id=embedding_id,
        start_ms=start_ms,
        end_ms=start_ms + 3_000,
        body=body,
        search_text=body,
    )


def _ids(hits: Any) -> set[str]:
    return {h.chunk_id for h in hits}


@dataclass(frozen=True)
class Env:
    kind: str
    app_url: str | None = None
    minio: Any = None


@pytest.fixture(params=["fake", pytest.param("sql", marks=pytest.mark.integration)])
def env(request: pytest.FixtureRequest) -> Env:
    """Resolved before the event loop starts: the Postgres fixtures run migrations with
    asyncio.run."""
    if request.param == "fake":
        return Env(kind="fake")
    return Env(
        kind="sql",
        app_url=request.getfixturevalue("app_url"),
        minio=request.getfixturevalue("minio"),
    )


@contextlib.asynccontextmanager
async def _open(env: Env) -> AsyncGenerator[tuple[Any, Any], None]:
    """Yields (index, seed). `seed()` makes one tenant and one job that the index may write for."""
    if env.kind == "fake":
        fake = FakeSearchIndex()

        async def seed_fake() -> tuple[str, str]:
            tenant, job = f"tenant-{uuid.uuid4().hex[:8]}", f"job-{uuid.uuid4().hex[:8]}"
            fake.register_job(tenant, job)
            return tenant, job

        yield fake, seed_fake
        return

    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415 - Docker-only path

    from tests.integration.api_support import seed_tenant  # noqa: PLC0415
    from tests.integration.test_deletion import _seed, _storage  # noqa: PLC0415

    engine: AsyncEngine = create_async_engine(str(env.app_url))
    storage = _storage(env.minio)
    search = _mod("transcribe_engine.infrastructure.search.pg_index")
    index = search.SqlSearchIndex(engine)

    async def seed_sql() -> tuple[str, str]:
        tenant = f"tenant-{uuid.uuid4().hex[:8]}"
        job = f"job-{uuid.uuid4().hex[:8]}"
        await seed_tenant(engine, tenant)
        digest = uuid.uuid4().hex * 2
        await _seed(engine, storage, tenant=tenant, job_id=job, sha=digest, result_key=f"rk-{job}")
        return tenant, job

    try:
        yield index, seed_sql
    finally:
        await engine.dispose()


async def test_active_version_is_the_only_one_searched(env: Env) -> None:
    """Positive control: v1 is found once active. While v2 is stored but not active, only v1 is
    found. After activating v2, only v2 is found. An older version cannot be activated over a newer
    one."""
    async with _open(env) as (index, seed):
        tenant, job = await seed()
        await index.store(
            tenant, job, "media", 1, MODEL, [_chunk("c1", "e1", "alpha beta")], {"e1": VECTOR}
        )
        await index.activate(tenant, job, 1)
        assert {h.version for h in await index.search(tenant, MODEL, "alpha", VECTOR, 10)} == {1}

        await index.store(
            tenant, job, "media", 2, MODEL, [_chunk("c2", "e2", "alpha gamma")], {"e2": VECTOR}
        )
        assert {h.version for h in await index.search(tenant, MODEL, "alpha", VECTOR, 10)} == {1}

        await index.activate(tenant, job, 2)
        assert {h.version for h in await index.search(tenant, MODEL, "alpha", VECTOR, 10)} == {2}

        await index.activate(tenant, job, 1)
        assert {h.version for h in await index.search(tenant, MODEL, "alpha", VECTOR, 10)} == {2}


async def test_reindex_replaces_the_version_rows(env: Env) -> None:
    """Positive control: the first run holds two chunks. A second run of the same version holds one
    chunk; only that one is left, with no duplicate and no chunk from the first run."""
    async with _open(env) as (index, seed):
        tenant, job = await seed()
        first = [_chunk("c1", "e1", "alpha one", 1_000), _chunk("c2", "e2", "alpha two", 5_000)]
        await index.store(tenant, job, "media", 1, MODEL, first, {"e1": VECTOR, "e2": VECTOR})
        await index.activate(tenant, job, 1)
        assert _ids(await index.chunks_of(tenant, job)) == {"c1", "c2"}

        await index.store(
            tenant, job, "media", 1, MODEL, [_chunk("c3", "e3", "alpha three")], {"e3": VECTOR}
        )
        assert _ids(await index.chunks_of(tenant, job)) == {"c3"}


async def test_writes_are_refused_for_an_unknown_job(env: Env) -> None:
    """A job that does not exist (or was deleted) takes no index rows. Positive control: a
    registered job takes its rows."""
    from transcribe_engine.application.errors import TranscriptNotFoundError  # noqa: PLC0415

    async with _open(env) as (index, seed):
        tenant, job = await seed()
        await index.store(
            tenant, job, "media", 1, MODEL, [_chunk("c1", "e1", "alpha")], {"e1": VECTOR}
        )
        with pytest.raises(TranscriptNotFoundError):
            await index.store(
                tenant,
                f"ghost-{job}",
                "media",
                1,
                MODEL,
                [_chunk("c2", "e2", "alpha")],
                {"e2": VECTOR},
            )


async def test_a_tenant_never_sees_another_tenants_text(env: Env) -> None:
    """Positive control: the owning tenant finds its text. The other tenant finds nothing for the
    same words, and cannot list the transcript's chunks."""
    async with _open(env) as (index, seed):
        owner, job = await seed()
        other, _ = await seed()
        await index.store(
            owner, job, "media", 1, MODEL, [_chunk("c1", "e1", "secretword here")], {"e1": VECTOR}
        )
        await index.activate(owner, job, 1)
        assert _ids(await index.search(owner, MODEL, "secretword", VECTOR, 10)) == {"c1"}
        assert await index.search(other, MODEL, "secretword", VECTOR, 10) == ()
        assert await index.chunks_of(other, job) == ()


async def test_no_match_and_other_model_give_nothing(env: Env) -> None:
    """Negative controls: a query word that is not in the text finds nothing, and so does a query
    through a different model. Positive control: the matching word with the same model is found."""
    async with _open(env) as (index, seed):
        tenant, job = await seed()
        await index.store(
            tenant, job, "media", 1, MODEL, [_chunk("c1", "e1", "alpha beta")], {"e1": VECTOR}
        )
        await index.activate(tenant, job, 1)
        assert _ids(await index.search(tenant, MODEL, "alpha", VECTOR, 10)) == {"c1"}
        assert await index.search(tenant, MODEL, "zzznever", VECTOR, 10) == ()
        assert await index.search(tenant, "other-model@9", "alpha", VECTOR, 10) == ()
