"""S20 metrics with real values (design: المراقبة).

Registered metrics are checked in unit tests; these check that the values move.

- Queue depth: after the reconciler runs, the gauge for a queue equals the queued jobs for it.
- Queue wait: the first claim of a job adds one observation to the wait histogram for its queue.
Positive control: each check compares against a count read from the database, not a constant.
"""

import importlib
from datetime import timedelta
from types import ModuleType

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


@pytest.mark.xfail(strict=True, reason="S20")
async def test_queue_depth_gauge_matches_queued_jobs(pg_url: str) -> None:
    engine = create_async_engine(pg_url)
    try:
        reconciler = _mod("transcribe_engine.infrastructure.db.reconciler")
        await reconciler.SqlReconciler(engine).run_once()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT set_config('app.system','on',true)"))
            queued = (
                await conn.execute(
                    text("SELECT count(*) FROM jobs WHERE state = 'QUEUED' AND queue = 'gpu'")
                )
            ).scalar_one()
        assert _sample("transcribe_queue_depth_jobs", {"queue": "gpu"}) == float(queued)
    finally:
        await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S20")
async def test_first_claim_observes_queue_wait(pg_url: str) -> None:
    engine = create_async_engine(pg_url)
    try:
        queue_mod = _mod("transcribe_engine.infrastructure.db.queue")
        before = _sample("transcribe_queue_wait_seconds_count", {"queue": "cpu"})
        claimed = await queue_mod.SqlJobQueue(engine).claim(
            "cpu", "metrics-test", timedelta(seconds=60)
        )
        if claimed is None:
            pytest.skip("no cpu job is queued in this database")
        job, _lease = claimed
        after = _sample("transcribe_queue_wait_seconds_count", {"queue": "cpu"})
        # Only a first attempt is a queue wait; a retried job is not counted again.
        assert after == before + (1.0 if job.attempt_count == 1 else 0.0)
    finally:
        await engine.dispose()
