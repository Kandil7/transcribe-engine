"""Worker loop behaviour (S06) on the fake queue: no sleeps, time moved only by the stub."""

import asyncio
from dataclasses import replace
from datetime import timedelta

from tests.fakes.clock import FakeClock
from tests.fakes.queue import FakeJobQueue
from tests.fakes.repositories import FakeStore
from transcribe_engine.application.worker_loop import WorkerSettings, run_once
from transcribe_engine.domain.config import PipelineConfig
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.domain.jobs import ErrorCode, Job, JobEvent, JobState, Media, transition

SETTINGS = WorkerSettings(
    queue_name="cpu", owner="w1", lease_for=timedelta(minutes=2), heartbeat_every=30.0
)


def _seed(store: FakeStore) -> None:
    config = PipelineConfig(
        engine="faster-whisper",
        model_revision="large-v3@r1",
        language="ar",
        decoding_params={"beam_size": 5},
        vad_params={"threshold": 0.5},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )
    store.media_by_tenant_sha[("tenant-a", "d" * 64)] = Media(
        id="media-w",
        tenant_id="tenant-a",
        sha256="d" * 64,
        storage_key="k",
        duration_ms=1,
        format="wav",
        size_bytes=1,
    )
    store.jobs["job-w"] = Job(
        id="job-w",
        tenant_id="tenant-a",
        media_id="media-w",
        state=JobState.QUEUED,
        stage=None,
        attempt_count=0,
        max_attempts=3,
        queue="cpu",
        config=config,
        result_id=None,
        error_code=None,
        warnings=(),
    )


async def _no_sleep(_: float) -> None:
    await asyncio.sleep(0)


async def test_completes_when_the_owner_keeps_its_lease() -> None:
    store = FakeStore()
    _seed(store)
    queue = FakeJobQueue(store, FakeClock())

    async def handler(job: Job) -> object:
        return transition(
            JobState.PROCESSING, JobEvent.SUCCEEDED, attempt_count=job.attempt_count, max_attempts=3
        )

    assert await run_once(queue, handler, SETTINGS, sleep=_no_sleep)
    assert store.jobs["job-w"].state == JobState.COMPLETED
    assert "job-w" not in store.leases


async def test_cancellation_discards_the_handler_output() -> None:
    store = FakeStore()
    _seed(store)
    queue = FakeJobQueue(store, FakeClock())
    never = asyncio.Event()

    async def handler(job: Job) -> object:
        await never.wait()  # a long stage that only cancellation interrupts
        return transition(
            JobState.PROCESSING, JobEvent.SUCCEEDED, attempt_count=job.attempt_count, max_attempts=3
        )

    beats = 0

    async def cancel_then_return(_: float) -> None:
        nonlocal beats
        beats += 1
        # Between two heartbeats, someone cancels the job.
        store.jobs["job-w"] = replace(store.jobs["job-w"], state=JobState.CANCELLED)

    assert await run_once(queue, handler, SETTINGS, sleep=cancel_then_return)
    assert beats >= 1  # the heartbeat really ran before the cancellation was observed
    assert store.jobs["job-w"].state == JobState.CANCELLED


class _SpyQueue:
    """Delegates to the fake queue and records whether complete was ever called."""

    def __init__(self, inner: FakeJobQueue) -> None:
        self._inner = inner
        self.completes = 0

    async def claim(self, queue: str, owner: str, lease_for: timedelta) -> object:
        return await self._inner.claim(queue, owner, lease_for)

    async def heartbeat(self, lease: object, extend_by: timedelta) -> object:
        return await self._inner.heartbeat(lease, extend_by)  # type: ignore[arg-type]

    async def complete(self, lease: object, t: object, *, stage: object = None) -> bool:
        self.completes += 1
        return await self._inner.complete(lease, t, stage=stage)  # type: ignore[arg-type]

    async def is_cancelled(self, job_id: str) -> bool:
        return await self._inner.is_cancelled(job_id)


async def test_transient_handler_error_schedules_a_retry() -> None:
    store = FakeStore()
    _seed(store)
    queue = FakeJobQueue(store, FakeClock())

    async def handler(job: Job) -> object:
        raise TransientError("object store blip")

    assert await run_once(queue, handler, SETTINGS, sleep=_no_sleep)  # type: ignore[arg-type]
    assert store.jobs["job-w"].state == JobState.RETRY_SCHEDULED
    assert store.jobs["job-w"].error_code is None


async def test_permanent_handler_error_fails_the_job() -> None:
    store = FakeStore()
    _seed(store)
    queue = FakeJobQueue(store, FakeClock())

    async def handler(job: Job) -> object:
        raise PermanentError("corrupt media")

    assert await run_once(queue, handler, SETTINGS, sleep=_no_sleep)  # type: ignore[arg-type]
    assert store.jobs["job-w"].state == JobState.FAILED
    assert store.jobs["job-w"].error_code == ErrorCode.INTERNAL


async def test_lost_lease_cancels_the_handler_and_never_completes() -> None:
    store = FakeStore()
    _seed(store)
    inner = FakeJobQueue(store, FakeClock())
    spy = _SpyQueue(inner)
    never = asyncio.Event()

    async def handler(job: Job) -> object:
        await never.wait()
        raise AssertionError("handler must be cancelled, not finish")

    async def reclaim_lease(_: float) -> None:
        store.leases.pop("job-w", None)  # someone else reclaimed the lease

    assert await run_once(spy, handler, SETTINGS, sleep=reclaim_lease)  # type: ignore[arg-type]
    assert spy.completes == 0
    assert store.jobs["job-w"].state == JobState.PROCESSING
