"""S10 PrepareChunks on fakes: VAD regions become a stored plan keyed to the job and the media hash.

Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType
from typing import Any

RATE = 16_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def test_plan_is_stored_for_the_job_and_media_hash() -> None:
    """Positive control: the planned chunks round-trip with the job's id, the media hash and the
    config hash. A second preparation of the same job leaves the stored plan unchanged."""
    fakes_repo = _mod("tests.fakes.repositories")
    fakes_vad = _mod("tests.fakes.vad")
    prepare = _mod("transcribe_engine.application.use_cases.prepare_chunks")
    vad_port = _mod("transcribe_engine.application.ports.vad")
    chunks_mod = _mod("transcribe_engine.domain.chunks")
    jobs_mod = _mod("transcribe_engine.domain.jobs")
    config = _mod("transcribe_engine.domain.config").PipelineConfig(
        engine="faster-whisper",
        model_revision="pending-s00",
        language="ar",
        decoding_params={},
        vad_params={},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )
    job: Any = jobs_mod.Job(
        id="job-p",
        tenant_id="tenant-a",
        media_id="media-p",
        state=jobs_mod.JobState.PENDING_VALIDATION,
        stage=None,
        attempt_count=1,
        max_attempts=3,
        queue="cpu",
        config=config,
        result_id=None,
        error_code=None,
        warnings=(),
    )
    vad = fakes_vad.FakeVad(
        vad_port.VadResult(
            total_samples=2 * RATE,
            regions=(
                chunks_mod.SpeechRegion(0, RATE),
                chunks_mod.SpeechRegion(RATE, 2 * RATE),
            ),
        )
    )
    store = fakes_repo.FakeStore()

    def make_uow(tenant_id: str | None = None) -> Any:
        return fakes_repo.FakeUnitOfWork(store)

    run = prepare.PrepareChunks(make_uow, vad, max_samples=RATE, pad=RATE // 10)
    await run(job, "f" * 64)
    await run(job, "f" * 64)
    async with make_uow("tenant-a") as uow:
        planned = await uow.chunks.plan("tenant-a", job.id)
    assert [c.idx for c in planned] == [0, 1]
    assert all(c.media_sha256 == "f" * 64 for c in planned)
    assert all(c.config_hash == config.config_hash() for c in planned)
    assert all(c.sample_rate == RATE for c in planned)


async def test_uses_engine_max_chunk_seconds() -> None:
    """AC-6. VAD runs in the CPU stage, and the plan respects the configured engine's maximum chunk
    length: no chunk core is longer than max_chunk_ms, and speech is still fully covered."""
    fakes_repo = _mod("tests.fakes.repositories")
    fakes_vad = _mod("tests.fakes.vad")
    prepare = _mod("transcribe_engine.application.use_cases.prepare_chunks")
    vad_port = _mod("transcribe_engine.application.ports.vad")
    chunks_mod = _mod("transcribe_engine.domain.chunks")
    jobs_mod = _mod("transcribe_engine.domain.jobs")
    config = _mod("transcribe_engine.domain.config").PipelineConfig(
        engine="faster-whisper",
        model_revision="pending-s00",
        language="ar",
        decoding_params={},
        vad_params={},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )
    job: Any = jobs_mod.Job(
        id="job-max",
        tenant_id="tenant-a",
        media_id="media-max",
        state=jobs_mod.JobState.PENDING_VALIDATION,
        stage=None,
        attempt_count=1,
        max_attempts=3,
        queue="cpu",
        config=config,
        result_id=None,
        error_code=None,
        warnings=(),
    )
    total = 40 * RATE
    vad = fakes_vad.FakeVad(
        vad_port.VadResult(
            total_samples=total,
            regions=(chunks_mod.SpeechRegion(0, 40 * RATE),),
        )
    )
    store = fakes_repo.FakeStore()

    def make_uow(tenant_id: str | None = None) -> Any:
        return fakes_repo.FakeUnitOfWork(store)

    run = prepare.PrepareChunks(
        make_uow,
        vad,
        max_samples=12 * RATE,
        pad=RATE // 5,
        target_samples=10 * RATE,
        overlap_samples=RATE * 3 // 2,
    )
    await run(job, "f" * 64)
    async with make_uow("tenant-a") as uow:
        planned = await uow.chunks.plan("tenant-a", job.id)
    assert planned
    assert all(c.end_sample - c.start_sample <= 12 * RATE for c in planned)
    assert planned[0].start_sample == 0
    assert planned[-1].end_sample == total
