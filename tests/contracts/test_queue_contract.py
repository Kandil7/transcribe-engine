"""Contract tests for the Postgres job queue, lease, fencing and reconciler (S06).

Run against the in-memory fakes and real Postgres. Expiry and retry need no sleeps: leases are
claimed with lease_for=0 (already expired) and retries use a zero backoff base (due at once).
A test that needs a retry to stay in the future uses a one-hour base.

Imports happen inside test bodies so the module collects before the implementation exists.
"""

import asyncio
import importlib
from collections.abc import Callable
from datetime import timedelta
from types import ModuleType

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.contract]

KINDS = ["fake", "postgres"]


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


class _Backend:
    """One backend: a unit-of-work factory, a queue, and a reconciler builder."""

    def __init__(
        self, make_uow: Callable[[], object], queue: object, reconcile: Callable[..., object]
    ) -> None:
        self.make_uow = make_uow
        self.queue = queue
        self.reconcile = reconcile


def _backend(kind: str, pg_url: str) -> _Backend:
    if kind == "fake":
        fakes_repo = _mod("tests.fakes.repositories")
        fakes_queue = _mod("tests.fakes.queue")
        fakes_clock = _mod("tests.fakes.clock")
        store = fakes_repo.FakeStore()
        clock = fakes_clock.FakeClock()
        queue = fakes_queue.FakeJobQueue(store, clock)

        def reconcile(backoff_base: timedelta = timedelta(0)) -> object:
            return fakes_queue.FakeReconciler(store, clock, backoff_base=backoff_base)

        return _Backend(lambda: fakes_repo.FakeUnitOfWork(store), queue, reconcile)
    sql_uow = _mod("transcribe_engine.infrastructure.db.uow")
    sql_queue = _mod("transcribe_engine.infrastructure.db.queue")
    sql_recon = _mod("transcribe_engine.infrastructure.db.reconciler")
    session = _mod("transcribe_engine.infrastructure.db.session")
    engine = session.make_engine(pg_url)

    def reconcile(backoff_base: timedelta = timedelta(0)) -> object:
        return sql_recon.SqlReconciler(engine, backoff_base=backoff_base)

    return _Backend(lambda: sql_uow.SqlUnitOfWork(engine), sql_queue.SqlJobQueue(engine), reconcile)


async def _seed(
    backend: _Backend, job_ids: list[str], *, priority: int = 0, max_attempts: int = 3
) -> None:
    """Insert one media row and the given QUEUED jobs for tenant-a."""
    jobs = _mod("transcribe_engine.domain.jobs")
    config = _mod("transcribe_engine.domain.config")
    media = jobs.Media(
        id="media-q",
        tenant_id="tenant-a",
        sha256="b" * 64,
        storage_key="incoming/tenant-a/q",
        duration_ms=60_000,
        format="mp3",
        size_bytes=1_000,
    )
    cfg = config.PipelineConfig(
        engine="faster-whisper",
        model_revision="large-v3@r1",
        language="ar",
        decoding_params={"beam_size": 5},
        vad_params={"threshold": 0.5},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )
    async with backend.make_uow() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(media)  # type: ignore[attr-defined]
        for job_id in job_ids:
            job = jobs.Job(
                id=job_id,
                tenant_id="tenant-a",
                media_id="media-q",
                state=jobs.JobState.QUEUED,
                stage=None,
                attempt_count=0,
                max_attempts=max_attempts,
                queue="cpu",
                config=cfg,
                result_id=None,
                error_code=None,
                warnings=(),
                priority=priority,
            )
            await uow.jobs.add(job)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]


async def _load(backend: _Backend, job_id: str) -> object:
    async with backend.make_uow() as uow:  # type: ignore[attr-defined]
        job = await uow.jobs.get("tenant-a", job_id)  # type: ignore[attr-defined]
    assert job is not None
    return job


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.xfail(strict=True, reason="S06")
async def test_fenced_complete_rejects_stale_owner(kind: str, pg_url: str) -> None:
    """AC-2: after a lease expires and the job is retried, the old owner's complete is refused."""
    jobs = _mod("transcribe_engine.domain.jobs")
    backend = _backend(kind, pg_url)
    await _seed(backend, ["job-fence"])
    _, stale = await backend.queue.claim("cpu", "worker-1", timedelta(0))  # type: ignore[attr-defined]
    await backend.reconcile().run_once(None)  # type: ignore[attr-defined]  # expiry, then retry due
    _, fresh = await backend.queue.claim("cpu", "worker-2", timedelta(minutes=10))  # type: ignore[attr-defined]
    assert fresh.attempt == stale.attempt + 1
    success = jobs.transition(
        jobs.JobState.PROCESSING,
        jobs.JobEvent.SUCCEEDED,
        attempt_count=fresh.attempt,
        max_attempts=3,
    )
    assert not await backend.queue.complete(stale, success)  # type: ignore[attr-defined]
    assert await backend.queue.complete(fresh, success)  # type: ignore[attr-defined]
    final = await _load(backend, "job-fence")
    assert final.state == jobs.JobState.COMPLETED  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.xfail(strict=True, reason="S06")
async def test_expired_lease_retried_then_poison(kind: str, pg_url: str) -> None:
    """AC-3: three expired leases in a row (max_attempts 3) end in FAILED with POISON_JOB."""
    jobs = _mod("transcribe_engine.domain.jobs")
    backend = _backend(kind, pg_url)
    await _seed(backend, ["job-poison"], max_attempts=3)
    for _ in range(3):
        claimed = await backend.queue.claim("cpu", "crashy", timedelta(0))  # type: ignore[attr-defined]
        assert claimed is not None
        await backend.reconcile().run_once(None)  # type: ignore[attr-defined]
    final = await _load(backend, "job-poison")
    assert final.state == jobs.JobState.FAILED  # type: ignore[attr-defined]
    assert final.error_code == jobs.ErrorCode.POISON_JOB  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.xfail(strict=True, reason="S06")
async def test_retry_due_requeues(kind: str, pg_url: str) -> None:
    """AC-4: a retry with a past run_after is requeued; one scheduled in the future is not."""
    jobs = _mod("transcribe_engine.domain.jobs")
    backend = _backend(kind, pg_url)
    await _seed(backend, ["job-due", "job-later"])
    await backend.queue.claim("cpu", "w", timedelta(0))  # type: ignore[attr-defined]
    await backend.queue.claim("cpu", "w", timedelta(0))  # type: ignore[attr-defined]
    await backend.reconcile(timedelta(0)).run_once(None)  # type: ignore[attr-defined]
    assert (await _load(backend, "job-due")).state == jobs.JobState.QUEUED  # type: ignore[attr-defined]
    assert (await _load(backend, "job-later")).state == jobs.JobState.QUEUED  # type: ignore[attr-defined]

    await backend.queue.claim("cpu", "w", timedelta(0))  # type: ignore[attr-defined]
    await backend.queue.claim("cpu", "w", timedelta(0))  # type: ignore[attr-defined]
    await backend.reconcile(timedelta(hours=1)).run_once(None)  # type: ignore[attr-defined]
    assert (await _load(backend, "job-due")).state == jobs.JobState.RETRY_SCHEDULED  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.xfail(strict=True, reason="S06")
async def test_cancel_observed_on_heartbeat(kind: str, pg_url: str) -> None:
    """AC-6: a job cancelled while running makes its next heartbeat raise JobCancelledError."""
    jobs = _mod("transcribe_engine.domain.jobs")
    errors = _mod("transcribe_engine.domain.errors")
    backend = _backend(kind, pg_url)
    await _seed(backend, ["job-cancel"])
    _, lease = await backend.queue.claim("cpu", "w", timedelta(minutes=10))  # type: ignore[attr-defined]
    cancel = jobs.transition(
        jobs.JobState.PROCESSING, jobs.JobEvent.CANCEL_REQUESTED, attempt_count=1, max_attempts=3
    )
    async with backend.make_uow() as uow:  # type: ignore[attr-defined]
        assert await uow.jobs.apply("job-cancel", cancel, expected=jobs.JobState.PROCESSING)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    assert await backend.queue.is_cancelled("job-cancel")  # type: ignore[attr-defined]
    with pytest.raises(errors.JobCancelledError):
        await backend.queue.heartbeat(lease, timedelta(minutes=2))  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.xfail(strict=True, reason="S06")
async def test_priority_then_fifo(kind: str, pg_url: str) -> None:
    """AC-7: higher priority first; equal priority in insertion order."""
    backend = _backend(kind, pg_url)
    await _seed(backend, ["low-a", "low-c"], priority=0)
    async with backend.make_uow() as uow:  # type: ignore[attr-defined]
        jobs = _mod("transcribe_engine.domain.jobs")
        high_b = _job_like(jobs, "high-b", priority=5)
        high_d = _job_like(jobs, "high-d", priority=5)
        await uow.jobs.add(high_b)  # type: ignore[attr-defined]
        await uow.jobs.add(high_d)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    order = []
    for _ in range(4):
        claimed = await backend.queue.claim("cpu", "w", timedelta(minutes=10))  # type: ignore[attr-defined]
        assert claimed is not None
        order.append(claimed[0].id)  # type: ignore[attr-defined]
    assert order == ["high-b", "high-d", "low-a", "low-c"]


def _job_like(jobs: ModuleType, job_id: str, priority: int) -> object:
    config = _mod("transcribe_engine.domain.config")
    return jobs.Job(
        id=job_id,
        tenant_id="tenant-a",
        media_id="media-q",
        state=jobs.JobState.QUEUED,
        stage=None,
        attempt_count=0,
        max_attempts=3,
        queue="cpu",
        config=config.PipelineConfig(
            engine="faster-whisper",
            model_revision="large-v3@r1",
            language="ar",
            decoding_params={"beam_size": 5},
            vad_params={"threshold": 0.5},
            diarization_enabled=False,
            pipeline_version="1.0.0",
        ),
        result_id=None,
        error_code=None,
        warnings=(),
        priority=priority,
    )


@pytest.mark.xfail(strict=True, reason="S06")
async def test_concurrent_claims_unique(pg_url: str) -> None:
    """AC-1: 200 jobs, 16 concurrent claimers on Postgres: each job is claimed exactly once."""
    backend = _backend("postgres", pg_url)
    ids = [f"bulk-{index:03d}" for index in range(200)]
    await _seed(backend, ids)

    async def drain() -> list[str]:
        claimed_ids: list[str] = []
        while (
            claim := await backend.queue.claim("cpu", "drainer", timedelta(minutes=10))
        ) is not None:  # type: ignore[attr-defined]
            claimed_ids.append(claim[0].id)  # type: ignore[attr-defined]
        return claimed_ids

    per_worker = await asyncio.gather(*(drain() for _ in range(16)))
    claimed = [job_id for worker in per_worker for job_id in worker]
    assert len(claimed) == 200
    assert len(set(claimed)) == 200
