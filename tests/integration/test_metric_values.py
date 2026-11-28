"""S20 metrics with real values (design: المراقبة).

Registered metrics are checked in unit tests; these check that the values move.

- Queue depth: after the reconciler runs, the gauge for a queue equals the queued jobs for it.
- Queue wait: the first claim of a job adds one observation to the wait histogram for its queue.
Positive control: each check compares against a count read from the database, not a constant.
"""

import importlib
from datetime import timedelta
from types import ModuleType
from uuid import uuid4

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [pytest.mark.integration]


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _sample(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else float(value)


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


async def _seed_queued_job(engine: object, queue: str) -> None:
    """One fresh QUEUED job on the queue, so a count or a claim has something to see."""
    jobs = _mod("transcribe_engine.domain.jobs")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    media = jobs.Media(
        id="media-metric",
        tenant_id="tenant-a",
        sha256="d" * 64,
        storage_key="incoming/tenant-a/metric",
        duration_ms=1_000,
        format="wav",
        size_bytes=1_000,
    )
    async with uow_mod.SqlUnitOfWork(engine, tenant_id=None) as uow:  # type: ignore[arg-type]
        await uow.media.upsert(media)
        await uow.jobs.add(
            jobs.Job(
                id=f"job-metric-{queue}-{uuid4().hex}",
                tenant_id="tenant-a",
                media_id="media-metric",
                state=jobs.JobState.QUEUED,
                stage=None,
                attempt_count=0,
                max_attempts=3,
                queue=queue,
                config=_config(),  # type: ignore[arg-type]
                result_id=None,
                error_code=None,
                warnings=(),
            )
        )
        await uow.commit()


async def _clear_metric_jobs(pg_url: str) -> None:
    """Remove the jobs this module queued. The queue contract shares this database and claims any
    queued job on its queue, so a leftover QUEUED row would be someone else's job to it."""
    engine = create_async_engine(pg_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM jobs WHERE id LIKE 'job-metric-%'"))
            await conn.execute(text("DELETE FROM media WHERE id = 'media-metric'"))
    finally:
        await engine.dispose()


async def test_queue_depth_gauge_matches_queued_jobs(pg_url: str) -> None:
    engine = create_async_engine(pg_url)
    try:
        reconciler = _mod("transcribe_engine.infrastructure.db.reconciler")
        await _seed_queued_job(engine, "gpu")  # positive control: the count is not zero
        await reconciler.SqlReconciler(engine).run_once()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT set_config('app.system','on',true)"))
            queued = (
                await conn.execute(
                    text("SELECT count(*) FROM jobs WHERE state = 'QUEUED' AND queue = 'gpu'")
                )
            ).scalar_one()
        assert queued >= 1
        assert _sample("transcribe_queue_depth_jobs", {"queue": "gpu"}) == float(queued)
    finally:
        await engine.dispose()
        await _clear_metric_jobs(pg_url)


async def test_first_claim_observes_queue_wait(pg_url: str) -> None:
    engine = create_async_engine(pg_url)
    try:
        queue_mod = _mod("transcribe_engine.infrastructure.db.queue")
        before = _sample("transcribe_queue_wait_seconds_count", {"queue": "cpu"})
        await _seed_queued_job(engine, "cpu")
        claimed = await queue_mod.SqlJobQueue(engine).claim(
            "cpu", "metrics-test", timedelta(seconds=60)
        )
        assert claimed is not None
        job, _lease = claimed
        after = _sample("transcribe_queue_wait_seconds_count", {"queue": "cpu"})
        # Only a first attempt is a queue wait; a retried job is not counted again.
        assert after == before + (1.0 if job.attempt_count == 1 else 0.0)
    finally:
        await engine.dispose()
        await _clear_metric_jobs(pg_url)
