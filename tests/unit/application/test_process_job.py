"""S10 ProcessJob on fakes: AC-8 (permanent chunk failure, both tenant settings) and the resume
behaviour behind AC-7 (a crash does not re-run stored chunks).

Each refusal is paired with a positive control (no failure, full transcript), so a use case that
always fails or always completes cannot pass. Imports happen inside helpers so the module collects.
"""

import asyncio
import contextlib
import importlib
from dataclasses import replace
from types import ModuleType
from typing import Any

import pytest

from transcribe_engine.domain.errors import PermanentError

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


class _GaugeASR:
    """Counts in-flight ASR calls. Each call yields to the loop so overlap is observable."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.active = 0
        self.peak = 0

    async def transcribe(self, audio_key: str, chunk: Any, *, language: str) -> Any:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.01)
            return await self._inner.transcribe(audio_key, chunk, language=language)
        finally:
            self.active -= 1


async def test_inflight_bounded() -> None:
    """S12 AC-4: never more than `concurrency` ASR calls in flight. Positive control: the bound is
    reached (peak == 2), so a use case that serialises everything cannot pass."""
    job = _job()
    plan = _plan(job)
    assert len(plan) > 2
    _, make_uow = await _seeded(job, plan)
    gauge = _GaugeASR(_mod("tests.fakes.asr").FakeASR(script=_script(plan)))
    result = await _process(make_uow, gauge, concurrency=2)(job)
    assert result.to is _mod("transcribe_engine.domain.jobs").JobState.COMPLETED
    assert gauge.peak == 2


def _dia(diarizer: Any, split: bool = False) -> Any:
    process = _mod("transcribe_engine.application.use_cases.process_job")
    return process.Diarization(diarizer=diarizer, split_channels=split)


async def test_diarization_failure_is_warning() -> None:
    """AC-3 (S17): a diarizer that fails leaves the job COMPLETED with `diarization_failed` and a
    transcript without speakers. Positive control: the same job with a working diarizer gets
    speakers and no warning."""
    helpers = _mod("tests.unit.application.test_process_job")
    jobs = _mod("transcribe_engine.domain.jobs")
    fakes_asr = _mod("tests.fakes.asr")
    fakes_dia = _mod("tests.fakes.diarizer")
    speakers = _mod("transcribe_engine.domain.speakers")
    base = helpers._job()
    job = replace(base, config=replace(base.config, diarization_enabled=True))
    plan = helpers._plan(job)
    _, make_uow = await helpers._seeded(job, plan)
    asr = fakes_asr.FakeASR(script=helpers._script(plan))

    failing = fakes_dia.FakeDiarizer(error=PermanentError("model refused"))
    result = await helpers._process(make_uow, asr, diarization=_dia(failing))(job)
    assert result.to is jobs.JobState.COMPLETED
    assert jobs.Warning.DIARIZATION_FAILED.value in result.warnings
    async with make_uow("tenant-a") as uow:
        words = (await uow.chunks.transcript("tenant-a", job.id)).words
    assert all(w.speaker is None for w in words)

    turns = (speakers.SpeakerTurn("SPEAKER_00", 0, 10_000),)
    working = fakes_dia.FakeDiarizer(turns=turns)
    ok = await helpers._process(make_uow, asr, diarization=_dia(working))(job)
    assert jobs.Warning.DIARIZATION_FAILED.value not in ok.warnings
    async with make_uow("tenant-a") as uow:
        speaker_words = (await uow.chunks.transcript("tenant-a", job.id)).words
    assert {w.speaker for w in speaker_words} == {"SPEAKER_00"}


async def test_split_channels_skip_diarization() -> None:
    """AC-6 (S17): a file split by channel (S13) is not diarized; the channel is the speaker.

    Positive control: the same job without the split is diarized."""
    helpers = _mod("tests.unit.application.test_process_job")
    fakes_asr = _mod("tests.fakes.asr")
    fakes_dia = _mod("tests.fakes.diarizer")
    base = helpers._job()
    job = replace(base, config=replace(base.config, diarization_enabled=True))
    plan = helpers._plan(job)
    _, make_uow = await helpers._seeded(job, plan)
    asr = fakes_asr.FakeASR(script=helpers._script(plan))

    split = fakes_dia.FakeDiarizer()
    await helpers._process(make_uow, asr, diarization=_dia(split, True))(job)
    assert split.calls == []

    whole = fakes_dia.FakeDiarizer()
    await helpers._process(make_uow, asr, diarization=_dia(whole, False))(job)
    assert len(whole.calls) == 1


async def test_unprepared_job_is_retried_not_completed() -> None:
    """The fence (S10 race): a job whose plan was never committed must not complete empty.

    ProcessJob raises a transient error so the job is retried. Positive control: a prepared
    file with an empty plan (silence) still completes.
    """
    helpers = _mod("tests.unit.application.test_process_job")
    fakes_asr = _mod("tests.fakes.asr")
    errors = _mod("transcribe_engine.domain.errors")
    job = helpers._job()
    fakes_repo = _mod("tests.fakes.repositories")
    store = fakes_repo.FakeStore()

    def make_uow(tenant_id: str | None = None) -> Any:
        return fakes_repo.FakeUnitOfWork(store)

    asr = fakes_asr.FakeASR()
    with pytest.raises(errors.TransientError):
        await helpers._process(make_uow, asr)(job)

    async with make_uow("tenant-a") as uow:
        await uow.chunks.add_plan("tenant-a", job.id, ())  # prepared, and silent
        await uow.commit()
    result = await helpers._process(make_uow, asr)(job)
    assert result.to == _mod("transcribe_engine.domain.jobs").JobState.COMPLETED


@pytest.mark.xfail(strict=True, reason="S14")
async def test_fallback_chunks_are_reported_as_warnings() -> None:
    """A chunk whose words came from segment times (alignment failed) is reported as
    `alignment_fallback:<idx>`; the job still completes (D-077).

    Positive control: the same job with aligned words reports no fallback warning.
    """
    helpers = _mod("tests.unit.application.test_process_job")
    fakes_asr = _mod("tests.fakes.asr")
    merge = _mod("transcribe_engine.domain.merge")
    job = helpers._job()
    plan = helpers._plan(job)
    _, make_uow = await helpers._seeded(job, plan)
    fallback_script = {
        chunk.chunk_id: (merge.RawWord("alpha", 10, 50, None, fallback=True),) for chunk in plan
    }
    result = await helpers._process(make_uow, fakes_asr.FakeASR(script=fallback_script))(job)
    assert "alignment_fallback:0" in result.warnings

    _, make_clean = await helpers._seeded(job, plan)
    clean = await helpers._process(make_clean, fakes_asr.FakeASR(script=helpers._script(plan)))(job)
    assert not [w for w in clean.warnings if w.startswith("alignment_fallback")]
