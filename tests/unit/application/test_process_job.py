"""S10 ProcessJob on fakes: AC-8 (permanent chunk failure, both tenant settings) and the resume
behaviour behind AC-7 (a crash does not re-run stored chunks).

Each refusal is paired with a positive control (no failure, full transcript), so a use case that
always fails or always completes cannot pass. Imports happen inside helpers so the module collects.
"""

import contextlib
import importlib
from types import ModuleType
from typing import Any

RATE = 1000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _config() -> Any:
    return _mod("transcribe_engine.domain.config").PipelineConfig(
        engine="faster-whisper",
        model_revision="pending-s00",
        language="ar",
        decoding_params={"temperature": 0.0},
        vad_params={},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )


def _job() -> Any:
    jobs = _mod("transcribe_engine.domain.jobs")
    return jobs.Job(
        id="job-1",
        tenant_id="tenant-a",
        media_id="media-1",
        state=jobs.JobState.PROCESSING,
        stage=None,
        attempt_count=1,
        max_attempts=3,
        queue="gpu",
        config=_config(),
        result_id=None,
        error_code=None,
        warnings=(),
    )


def _plan(job: Any) -> tuple[Any, ...]:
    chunks = _mod("transcribe_engine.domain.chunks")
    regions = [
        chunks.SpeechRegion(0, 300),
        chunks.SpeechRegion(300, 600),
        chunks.SpeechRegion(900, 1_200),
    ]
    return chunks.plan_chunks(
        regions,
        max_samples=300,
        pad=0,
        total_samples=1_200,
        sample_rate=RATE,
        media_sha256="a" * 64,
        config_hash=job.config.config_hash(),
        job_id=job.id,
    )


def _script(plan: tuple[Any, ...]) -> dict[str, tuple[Any, ...]]:
    merge = _mod("transcribe_engine.domain.merge")
    words = [
        merge.RawWord("alpha", 10, 50, None),
        merge.RawWord("beta", 5, 25, None),
        merge.RawWord("gamma", 0, 100, None),
    ]
    return {chunk.chunk_id: (words[chunk.idx],) for chunk in plan}


async def _seeded(job: Any, plan: tuple[Any, ...]) -> tuple[Any, Any]:
    fakes_repo = _mod("tests.fakes.repositories")
    store = fakes_repo.FakeStore()

    def make_uow(tenant_id: str | None = None) -> Any:
        return fakes_repo.FakeUnitOfWork(store)

    async with make_uow("tenant-a") as uow:
        await uow.chunks.add_plan("tenant-a", job.id, plan)
        await uow.commit()
    return store, make_uow


def _process(make_uow: Any, asr: Any, **settings: Any) -> Any:
    process = _mod("transcribe_engine.application.use_cases.process_job")
    return process.ProcessJob(make_uow, asr, **settings)


async def test_positive_control_completes_with_every_word() -> None:
    """No failures: COMPLETED, no chunk warning, and all three words in order."""
    jobs = _mod("transcribe_engine.domain.jobs")
    fakes_asr = _mod("tests.fakes.asr")
    job = _job()
    plan = _plan(job)
    _, make_uow = await _seeded(job, plan)
    asr = fakes_asr.FakeASR(script=_script(plan))
    result = await _process(make_uow, asr)(job)
    assert result.to is jobs.JobState.COMPLETED
    assert result.warnings == ()
    async with make_uow("tenant-a") as uow:
        transcript = await uow.chunks.transcript("tenant-a", job.id)
    assert [w.text for w in transcript.words] == ["alpha", "beta", "gamma"]


async def test_permanent_chunk_failure_completes_with_a_gap_when_partial_is_allowed() -> None:
    """AC-8, tenant allows partial text: COMPLETED, warning chunk_failed:1, the gap has no words."""
    jobs = _mod("transcribe_engine.domain.jobs")
    fakes_asr = _mod("tests.fakes.asr")
    job = _job()
    plan = _plan(job)
    _, make_uow = await _seeded(job, plan)
    asr = fakes_asr.FakeASR(script=_script(plan), fail_permanent={plan[1].chunk_id})
    result = await _process(make_uow, asr, require_complete_text=False)(job)
    assert result.to is jobs.JobState.COMPLETED
    assert "chunk_failed:1" in result.warnings
    async with make_uow("tenant-a") as uow:
        transcript = await uow.chunks.transcript("tenant-a", job.id)
    assert [w.text for w in transcript.words] == ["alpha", "gamma"]


async def test_permanent_chunk_failure_fails_the_job_when_complete_text_is_required() -> None:
    """AC-8, tenant requires complete text: the job fails, and no transcript is stored."""
    jobs = _mod("transcribe_engine.domain.jobs")
    fakes_asr = _mod("tests.fakes.asr")
    job = _job()
    plan = _plan(job)
    _, make_uow = await _seeded(job, plan)
    asr = fakes_asr.FakeASR(script=_script(plan), fail_permanent={plan[1].chunk_id})
    result = await _process(make_uow, asr, require_complete_text=True)(job)
    assert result.to is jobs.JobState.FAILED
    assert result.error_code is jobs.ErrorCode.INTERNAL
    async with make_uow("tenant-a") as uow:
        assert await uow.chunks.transcript("tenant-a", job.id) is None


class _CrashingASR:
    """Delegates to the fake, but crashes once on chunk 1, as a killed worker would."""

    def __init__(self, inner: Any, crash_on_idx: int) -> None:
        self._inner = inner
        self._crash_on_idx = crash_on_idx
        self._crashed = False

    async def transcribe(self, audio_key: str, chunk: Any, *, language: str) -> Any:
        if chunk.idx == self._crash_on_idx and not self._crashed:
            self._crashed = True
            raise RuntimeError("worker killed")
        return await self._inner.transcribe(audio_key, chunk, language=language)


async def test_resume_after_a_crash_does_not_reprocess_stored_chunks() -> None:
    """AC-7 (unit form). Chunk 0 is stored before the crash; after the restart it is not sent to
    the ASR again, and the job completes with every word."""
    jobs = _mod("transcribe_engine.domain.jobs")
    fakes_asr = _mod("tests.fakes.asr")
    job = _job()
    plan = _plan(job)
    _, make_uow = await _seeded(job, plan)
    inner = fakes_asr.FakeASR(script=_script(plan))
    first_run = _process(make_uow, _CrashingASR(inner, crash_on_idx=1), concurrency=1)
    with contextlib.suppress(ExceptionGroup):
        await first_run(job)
    assert inner.calls[plan[0].chunk_id] == 1
    result = await _process(make_uow, inner)(job)
    assert result.to is jobs.JobState.COMPLETED
    assert inner.calls[plan[0].chunk_id] == 1  # the stored chunk was not transcribed again
    async with make_uow("tenant-a") as uow:
        transcript = await uow.chunks.transcript("tenant-a", job.id)
    assert [w.text for w in transcript.words] == ["alpha", "beta", "gamma"]
