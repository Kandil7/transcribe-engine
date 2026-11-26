"""AC-1 (S20): the outbox row is written in the same transaction as the job's state change.

Real Postgres. Positive control: the completed job has exactly one transcript.completed row whose
payload names the job and the webhook destination. Rollback: a state change that is rolled back
leaves no event and the job keeps its state. Both fail if the outbox write is missing or runs
outside the transaction.
"""

import importlib
from datetime import UTC, datetime, timedelta
from types import ModuleType

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.contract]

OWNER = "s20-owner"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _config() -> object:
    config = _mod("transcribe_engine.domain.config")
    return config.PipelineConfig(
        engine="faster-whisper",
        model_revision="large-v3@r1",
        language="ar",
        decoding_params={"beam_size": 5},
        vad_params={"threshold": 0.5},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )


async def _seed_processing(engine: AsyncEngine, job_id: str) -> object:
    """A PROCESSING job under a live lease, written through the real repositories."""
    jobs = _mod("transcribe_engine.domain.jobs")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    queue_port = _mod("transcribe_engine.application.ports.queue")
    media = jobs.Media(
        id="media-s20-ac1",
        tenant_id="tenant-a",
        sha256="e" * 64,
        storage_key="incoming/tenant-a/s20-ac1",
        duration_ms=1_000,
        format="wav",
        size_bytes=1_000,
    )
    async with uow_mod.SqlUnitOfWork(engine, tenant_id=None) as uow:  # type: ignore[arg-type]
        stored = await uow.media.upsert(media)
        await uow.jobs.add(
            jobs.Job(
                id=job_id,
                tenant_id="tenant-a",
                media_id=stored.id,
                state=jobs.JobState.QUEUED,
                stage=None,
                attempt_count=0,
                max_attempts=3,
                queue="gpu",
                config=_config(),  # type: ignore[arg-type]
                result_id=None,
                error_code=None,
                warnings=(),
                webhook_url="https://hook.public.test/s20",
            )
        )
        await uow.commit()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE jobs SET state = 'PROCESSING', attempt_count = 1, lease_owner = :owner, "
                "lease_until = now() + interval '1 hour' WHERE id = :id"
            ),
            {"owner": OWNER, "id": job_id},
        )
    return queue_port.Lease(
        job_id=job_id,
        owner=OWNER,
        attempt=1,
        until=datetime.now(UTC) + timedelta(hours=1),
    )


async def _events_for(engine: AsyncEngine, job_id: str) -> list[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT event FROM outbox WHERE payload->>'job_id' = :id ORDER BY id"),
            {"id": job_id},
        )
        return [row.event for row in rows]


async def test_event_written_with_state_change(pg_url: str) -> None:
    """AC-1: completing a job writes one transcript.completed row in the same transaction."""
    jobs = _mod("transcribe_engine.domain.jobs")
    queue_mod = _mod("transcribe_engine.infrastructure.db.queue")
    engine = create_async_engine(pg_url)
    job_id = "s20-ac1-complete"
    try:
        lease = await _seed_processing(engine, job_id)
        queue = queue_mod.SqlJobQueue(engine)
        assert await queue.complete(lease, jobs.Transition(to=jobs.JobState.COMPLETED)) is True
        assert await _events_for(engine, job_id) == ["transcript.completed"]
        async with engine.connect() as conn:
            payload = (
                await conn.execute(
                    text("SELECT payload FROM outbox WHERE payload->>'job_id' = :id"),
                    {"id": job_id},
                )
            ).scalar_one()
        assert payload["webhook_url"] == "https://hook.public.test/s20"
        assert payload["tenant_id"] == "tenant-a"
    finally:
        await engine.dispose()


async def test_rolled_back_state_change_leaves_no_event(pg_url: str) -> None:
    """AC-1: when the transaction holding the state change rolls back, no event survives and the
    job keeps its state."""
    jobs = _mod("transcribe_engine.domain.jobs")
    queue_mod = _mod("transcribe_engine.infrastructure.db.queue")
    session = _mod("transcribe_engine.infrastructure.db.session")
    engine = create_async_engine(pg_url)
    job_id = "s20-ac1-rollback"
    try:
        lease = await _seed_processing(engine, job_id)

        async def _complete_then_fail() -> bool:
            async with engine.begin() as conn:
                await conn.execute(session.SYSTEM_SCOPE)
                written = await queue_mod.complete_in(
                    conn, lease, jobs.Transition(to=jobs.JobState.COMPLETED)
                )
                assert written is True
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await _complete_then_fail()
        assert await _events_for(engine, job_id) == []
        async with engine.connect() as conn:
            state = (
                await conn.execute(text("SELECT state FROM jobs WHERE id = :id"), {"id": job_id})
            ).scalar_one()
        assert state == "PROCESSING"
    finally:
        await engine.dispose()
