"""Contract tests for the repositories and unit of work (S05). Run against the in-memory fakes and
real Postgres (Testcontainers, migrations applied with Alembic).

Imports happen inside each test body so the module collects before the implementation exists.
"""

import asyncio
import importlib
import os
import re
from collections.abc import Callable, Iterator
from types import ModuleType

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from tests.integration.test_migrations import _alembic_config

pytestmark = [pytest.mark.integration, pytest.mark.contract]

KINDS = [
    "fake",
    pytest.param("postgres", marks=pytest.mark.xfail(strict=True, reason="S05")),
]


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """A migrated Postgres. The URL is asyncpg-qualified for SQLAlchemy."""
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        dsn = "postgresql+asyncpg://" + pg.get_connection_url().split("://", 1)[1]
        previous = os.environ.get("TE_DATABASE_URL")
        os.environ["TE_DATABASE_URL"] = dsn
        try:
            command.upgrade(_alembic_config(), "head")
            yield dsn
        finally:
            if previous is None:
                os.environ.pop("TE_DATABASE_URL", None)
            else:
                os.environ["TE_DATABASE_URL"] = previous


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _factory(kind: str, pg_url: str) -> Callable[[], object]:
    """Unit-of-work factory for one backend. The fake shares one store across units of work."""
    if kind == "fake":
        fakes = _mod("tests.fakes.repositories")
        store = fakes.FakeStore()
        return lambda: fakes.FakeUnitOfWork(store)
    sql = _mod("transcribe_engine.infrastructure.db.uow")
    return lambda: sql.SqlUnitOfWork(pg_url)


def _job(job_id: str, tenant_id: str, media_id: str, state: str = "QUEUED") -> object:
    jobs = _mod("transcribe_engine.domain.jobs")
    config = _mod("transcribe_engine.domain.config")
    return jobs.Job(
        id=job_id,
        tenant_id=tenant_id,
        media_id=media_id,
        state=jobs.JobState(state),
        stage=None,
        attempt_count=0,
        max_attempts=3,
        queue="cpu",
        config=config.PipelineConfig(
            engine="faster-whisper",
            model_revision="large-v3@r1",
            language="ar",
            decoding_params={"beam_size": 5, "temperature": 0},
            vad_params={"threshold": 0.5},
            diarization_enabled=False,
            pipeline_version="1.0.0",
        ),
        result_id=None,
        error_code=None,
        warnings=(),
    )


def _media(media_id: str) -> object:
    jobs = _mod("transcribe_engine.domain.jobs")
    return jobs.Media(
        id=media_id,
        sha256="a" * 64,
        storage_key="incoming/tenant-a/upload-1",
        duration_ms=60_000,
        format="mp3",
        size_bytes=1_000_000,
    )


@pytest.mark.xfail(strict=True, reason="S05")
async def test_state_check_matches_domain(pg_url: str) -> None:
    """AC-1: the jobs.state CHECK constraint lists exactly the JobState values."""
    jobs = _mod("transcribe_engine.domain.jobs")
    engine = create_async_engine(pg_url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE t.relname = 'jobs' AND c.contype = 'c'"
                )
            )
            definitions = [row[0] for row in rows]
    finally:
        await engine.dispose()
    states = set()
    for definition in definitions:
        if "state" in definition:
            states |= set(re.findall(r"'([A-Z_]+)'", definition))
    assert states == {state.value for state in jobs.JobState}


@pytest.mark.parametrize("kind", KINDS)
async def test_claim_key_concurrent(kind: str, pg_url: str) -> None:
    """AC-2: 20 concurrent claims on one key give one creator, 19 readers and one row."""
    make = _factory(kind, pg_url)
    config = _job("job-x", "tenant-a", "media-1").config  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-1"))  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]

    async def claim() -> tuple[bool, str]:
        async with make() as uow:  # type: ignore[attr-defined]
            result, created = await uow.results.claim_key(  # type: ignore[attr-defined]
                "res_concurrent", "media-1", config
            )
            await uow.commit()  # type: ignore[attr-defined]
            return created, result.id

    outcomes = await asyncio.gather(*(claim() for _ in range(20)))
    assert sum(1 for created, _ in outcomes if created) == 1
    assert len({result_id for _, result_id in outcomes}) == 1


@pytest.mark.parametrize("kind", KINDS)
async def test_apply_compare_and_set(kind: str, pg_url: str) -> None:
    """AC-3: a stale expected state returns False and changes nothing."""
    jobs = _mod("transcribe_engine.domain.jobs")
    make = _factory(kind, pg_url)
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-2"))  # type: ignore[attr-defined]
        await uow.jobs.add(_job("job-cas", "tenant-a", "media-2"))  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    claimed = jobs.transition(
        jobs.JobState.QUEUED, jobs.JobEvent.CLAIMED, attempt_count=1, max_attempts=3
    )
    async with make() as uow:  # type: ignore[attr-defined]
        assert await uow.jobs.apply("job-cas", claimed, expected=jobs.JobState.QUEUED)  # type: ignore[attr-defined]
        assert not await uow.jobs.apply("job-cas", claimed, expected=jobs.JobState.QUEUED)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        job = await uow.jobs.get("tenant-a", "job-cas")  # type: ignore[attr-defined]
    assert job is not None
    assert job.state == jobs.JobState.PROCESSING


@pytest.mark.parametrize("kind", KINDS)
async def test_get_other_tenant_returns_none(kind: str, pg_url: str) -> None:
    """AC-4: a job is invisible to other tenants."""
    make = _factory(kind, pg_url)
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-3"))  # type: ignore[attr-defined]
        await uow.jobs.add(_job("job-iso", "tenant-a", "media-3"))  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        assert await uow.jobs.get("tenant-b", "job-iso") is None  # type: ignore[attr-defined]
        assert await uow.jobs.get("tenant-a", "job-iso") is not None  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", KINDS)
async def test_job_round_trip(kind: str, pg_url: str) -> None:
    """AC-5: every field survives save and load; the config's canonical JSON is byte-equal."""
    make = _factory(kind, pg_url)
    original = _job("job-rt", "tenant-a", "media-4")
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-4"))  # type: ignore[attr-defined]
        await uow.jobs.add(original)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        loaded = await uow.jobs.get("tenant-a", "job-rt")  # type: ignore[attr-defined]
    assert loaded == original
    assert loaded.config.canonical_json() == original.config.canonical_json()  # type: ignore[attr-defined]
