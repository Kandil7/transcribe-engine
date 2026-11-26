"""AC-5 (S06): workers die at random; no job is lost and none is completed twice.

Real Postgres, real short leases (1 s) and a running reconciler. The seed is fixed, so the set of
abandoned leases is the same on every run. This is the one S06 test that waits for real expiry.
"""

import asyncio
import importlib
import random
from datetime import timedelta
from types import ModuleType

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.contract]

SEED = 1234
JOB_COUNT = 1000
WORKERS = 8
ABANDON_RATE = 0.2
LEASE = timedelta(seconds=1)
TERMINAL_TIMEOUT_S = 240


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


async def _seed(engine: object, job_ids: list[str]) -> None:
    jobs = _mod("transcribe_engine.domain.jobs")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    media = jobs.Media(
        id="media-chaos",
        tenant_id="tenant-a",
        sha256="c" * 64,
        storage_key="incoming/tenant-a/chaos",
        duration_ms=1_000,
        format="wav",
        size_bytes=1_000,
    )
    async with uow_mod.SqlUnitOfWork(engine, tenant_id=None) as uow:  # type: ignore[arg-type]
        await uow.media.upsert(media)
        for job_id in job_ids:
            await uow.jobs.add(
                jobs.Job(
                    id=job_id,
                    tenant_id="tenant-a",
                    media_id="media-chaos",
                    state=jobs.JobState.QUEUED,
                    stage=None,
                    attempt_count=0,
                    max_attempts=3,
                    queue="cpu",
                    config=_config(),  # type: ignore[arg-type]
                    result_id=None,
                    error_code=None,
                    warnings=(),
                )
            )
        await uow.commit()


async def _worker(
    name: str,
    queue: object,
    abandon: dict[str, bool],
    completions: dict[str, int],
    stale: list[tuple[object, str]],
) -> None:
    """Claim until nothing is claimable. An abandoned first attempt sends no heartbeat, and its
    lease object is kept: after expiry it is the stale owner's proof (D-022)."""
    jobs = _mod("transcribe_engine.domain.jobs")
    while (claimed := await queue.claim("cpu", name, LEASE)) is not None:  # type: ignore[attr-defined]
        job, lease = claimed
        if abandon[job.id] and lease.attempt == 1:
            stale.append((lease, job.id))
            continue  # the worker "dies": the lease simply expires
        success = jobs.transition(
            jobs.JobState.PROCESSING,
            jobs.JobEvent.SUCCEEDED,
            attempt_count=lease.attempt,
            max_attempts=3,
        )
        if await queue.complete(lease, success):  # type: ignore[attr-defined]
            completions[job.id] = completions.get(job.id, 0) + 1


async def _reap_forever(reconciler: object) -> None:
    while True:
        await reconciler.run_once(None)  # type: ignore[attr-defined]
        await asyncio.sleep(0.2)


async def _all_terminal(engine: object, job_ids: list[str]) -> tuple[bool, list[str]]:
    jobs = _mod("transcribe_engine.domain.jobs")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    states: list[str] = []
    async with uow_mod.SqlUnitOfWork(engine, tenant_id=None) as uow:  # type: ignore[arg-type]
        for job_id in job_ids:
            job = await uow.jobs.get("tenant-a", job_id)
            assert job is not None
            states.append(job.state.value)
    terminal = {jobs.JobState.COMPLETED.value, jobs.JobState.FAILED.value}
    return all(state in terminal for state in states), states


async def test_kill_workers_no_loss_no_dup(pg_url: str) -> None:
    """AC-5: every job reaches a terminal state; no job is completed by two owners."""
    jobs = _mod("transcribe_engine.domain.jobs")
    queue_mod = _mod("transcribe_engine.infrastructure.db.queue")
    recon_mod = _mod("transcribe_engine.infrastructure.db.reconciler")
    session = _mod("transcribe_engine.infrastructure.db.session")

    engine = session.make_engine(pg_url)
    queue = queue_mod.SqlJobQueue(engine)
    reconciler = recon_mod.SqlReconciler(engine, backoff_base=timedelta(0))
    rng = random.Random(SEED)
    job_ids = [f"chaos-{i:04d}" for i in range(JOB_COUNT)]
    abandon = {job_id: rng.random() < ABANDON_RATE for job_id in job_ids}
    completions: dict[str, int] = {}
    stale: list[tuple[object, str]] = []

    await _seed(engine, job_ids)
    reaper = asyncio.create_task(_reap_forever(reconciler))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TERMINAL_TIMEOUT_S
    try:
        while True:
            await asyncio.gather(
                *(_worker(f"w{i}", queue, abandon, completions, stale) for i in range(WORKERS))
            )
            done, states = await _all_terminal(engine, job_ids)
            if done:
                break
            assert loop.time() < deadline, "jobs still non-terminal"
            await asyncio.sleep(1.5)  # let abandoned leases expire
    finally:
        reaper.cancel()
        await engine.dispose()

    assert stale, "no lease was abandoned, so the chaos run tested nothing"
    # Each abandoned owner now completes with its expired lease. The fence must refuse every one.
    success = jobs.transition(
        jobs.JobState.PROCESSING, jobs.JobEvent.SUCCEEDED, attempt_count=1, max_attempts=3
    )
    for lease, _job_id in stale:
        assert not await queue.complete(lease, success), "a stale owner completed a job"  # type: ignore[attr-defined]
    assert all(count <= 1 for count in completions.values()), "a job was completed twice"
    completed = sum(1 for state in states if state == jobs.JobState.COMPLETED.value)
    assert len(completions) == completed
