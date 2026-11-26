"""S15 AC-8 on fakes: the result use case renders every format and profile from the stored
transcript. Each refusal is paired with a positive control, so a use case that renders nothing
or everything the same cannot pass. Imports happen inside helpers so the module collects before
the code exists.
"""

import importlib
from types import ModuleType
from typing import Any

import pytest

RATE = 16_000
FORMATS = ("canonical", "txt", "md", "csv", "srt", "vtt")


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _config() -> Any:
    return _mod("transcribe_engine.domain.config").PipelineConfig(
        engine="faster-whisper",
        model_revision="rev-1",
        language="ar",
        decoding_params={"temperature": 0.0},
        vad_params={},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )


def _job(state: str) -> Any:
    jobs = _mod("transcribe_engine.domain.jobs")
    return jobs.Job(
        id="job-1",
        tenant_id="tenant-a",
        media_id="media-1",
        state=jobs.JobState(state),
        stage=None,
        attempt_count=1,
        max_attempts=3,
        queue="gpu",
        config=_config(),
        result_id=None,
        error_code=None,
        warnings=(),
    )


def _merged(texts: list[str], step_ms: int) -> Any:
    merge = _mod("transcribe_engine.domain.merge")
    words = tuple(
        merge.Word(
            text=text,
            start_ms=i * step_ms,
            end_ms=i * step_ms + step_ms - 50,
            conf=None,
            chunk_idx=0,
        )
        for i, text in enumerate(texts)
    )
    return merge.MergedWords(words=words, sample_rate=RATE)


async def _store(job: Any, merged: Any) -> Any:
    fakes_repo = _mod("tests.fakes.repositories")
    store = fakes_repo.FakeStore()

    def make_uow(tenant_id: str | None = None) -> Any:
        return fakes_repo.FakeUnitOfWork(store)

    async with make_uow("tenant-a") as uow:
        await uow.jobs.add(job)
        await uow.chunks.save_transcript("tenant-a", job.id, merged)
        await uow.commit()
    return make_uow


def _render(make_uow: Any) -> Any:
    return _mod("transcribe_engine.application.use_cases.render_result").RenderResult(make_uow)


async def test_formats_and_profiles() -> None:
    """AC-8 (unit form): every format renders non-empty bytes with a media type. Subtitles differ
    by profile on a fixture longer than the vertical profile allows, so the profile is applied."""
    make_uow = await _store(_job("COMPLETED"), _merged(["كلمة"] * 10, step_ms=500))
    render = _render(make_uow)
    for name in FORMATS:
        body = await render("tenant-a", "job-1", format=name)
        assert body.content
        assert body.media_type
    broadcast = await render("tenant-a", "job-1", format="srt", profile="broadcast")
    vertical = await render("tenant-a", "job-1", format="srt", profile="social_vertical")
    assert broadcast.content != vertical.content


async def test_unknown_format_and_profile_are_refused() -> None:
    """Refusals are 'unsupported feature'. Positive control: valid names still work."""
    unsupported = _mod("transcribe_engine.application.errors").UnsupportedFeatureError
    make_uow = await _store(_job("COMPLETED"), _merged(["عايز", "أروح"], step_ms=500))
    render = _render(make_uow)
    with pytest.raises(unsupported):
        await render("tenant-a", "job-1", format="docx")
    with pytest.raises(unsupported):
        await render("tenant-a", "job-1", format="srt", profile="unknown")
    assert (await render("tenant-a", "job-1", format="srt")).content


async def test_not_completed_job_is_not_ready() -> None:
    """A job that is not COMPLETED has no result yet. Positive control: a COMPLETED job renders."""
    not_ready = _mod("transcribe_engine.application.errors").ResultNotReadyError
    make_uow = await _store(_job("PROCESSING"), _merged(["عايز"], step_ms=500))
    with pytest.raises(not_ready):
        await _render(make_uow)("tenant-a", "job-1", format="txt")
    make_done = await _store(_job("COMPLETED"), _merged(["عايز"], step_ms=500))
    assert (await _render(make_done)("tenant-a", "job-1", format="txt")).content
