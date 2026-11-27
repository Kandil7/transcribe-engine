"""S20 tracing: ProcessJob opens one span per stage, linked by job_id.

Spans exist for the ASR and PERSISTING stages of a completed job.

Positive control: both spans close with status ok.
"""

import importlib
from types import ModuleType
from typing import Any

from tests.fakes.tracing import FakeTracer


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def test_process_job_opens_stage_spans() -> None:
    helpers = _mod("tests.unit.application.test_process_job")
    fakes_asr = _mod("tests.fakes.asr")
    job = helpers._job()
    plan = helpers._plan(job)
    _, make_uow = await helpers._seeded(job, plan)
    asr = fakes_asr.FakeASR(script=helpers._script(plan))
    tracer = FakeTracer()
    process = helpers._process(make_uow, asr, tracer=tracer)
    await process(job)
    stages = {(j, s): status for j, s, status in tracer.closed}
    assert stages[(job.id, "ASR")] == "ok"
    assert stages[(job.id, "PERSISTING")] == "ok"


async def test_ingest_opens_validating_and_normalizing_spans(tmp_path: Any) -> None:
    """A normal upload is probed (VALIDATING) and converted (NORMALIZING), each in its own span.

    Positive control: the same upload still hands off to the GPU queue (QUEUED).
    """
    helpers = _mod("tests.unit.application.test_ingest_job")
    jobs = _mod("transcribe_engine.domain.jobs")
    _, _, storage, probe, normalizer, make_uow = await helpers._world(b"x" * 10)
    tracer = FakeTracer()
    result = await helpers._ingest(storage, probe, normalizer, make_uow, tmp_path, tracer=tracer)(
        helpers._job()
    )
    assert result.to is jobs.JobState.QUEUED  # the hand-off to the GPU queue, as in test_handoff
    stages = {(j, s): status for j, s, status in tracer.closed}
    assert stages[("job-1", "VALIDATING")] == "ok"
    assert stages[("job-1", "NORMALIZING")] == "ok"


async def test_prepare_opens_vad_span() -> None:
    """Planning the chunks asks VAD for speech regions inside a VAD span.

    Positive control: the span closes with status ok after a real analysis.
    """
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
        id="job-v",
        tenant_id="tenant-a",
        media_id="media-v",
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
        vad_port.VadResult(total_samples=16_000, regions=(chunks_mod.SpeechRegion(0, 16_000),))
    )
    store = fakes_repo.FakeStore()

    def make_uow(tenant_id: str | None = None) -> Any:
        return fakes_repo.FakeUnitOfWork(store)

    tracer = FakeTracer()
    planner = prepare.PrepareChunks(make_uow, vad, max_samples=16_000, pad=0, tracer=tracer)
    await planner(job, "a" * 64)
    assert ("job-v", "VAD", "ok") in tracer.closed
