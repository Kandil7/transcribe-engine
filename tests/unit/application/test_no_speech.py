"""S13 AC-3 (unit, fakes): a file with no speech completes without any ASR call.

VAD finds no speech region, so the chunk plan is empty. The job completes with the `no_speech`
warning, and the ASR engine is never called. Positive control: a file with speech calls the ASR
for every chunk and carries no `no_speech` warning, so a use case that always completes cannot
pass.
"""

import importlib
from collections import Counter
from types import ModuleType

import pytest

from tests.unit.application.test_process_job import _job, _plan, _process, _script, _seeded


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


@pytest.mark.xfail(strict=True, reason="S13")
async def test_no_speech_completes_without_asr_calls() -> None:
    jobs = _mod("transcribe_engine.domain.jobs")
    fakes_asr = _mod("tests.fakes.asr")
    job = _job()
    _store, make_uow = await _seeded(job, ())
    asr = fakes_asr.FakeASR(script={})

    result = await _process(make_uow, asr)(job)

    assert asr.calls == Counter(), "no chunk exists, so the engine must not be called"
    assert result.to == jobs.JobState.COMPLETED
    assert jobs.Warning.NO_SPEECH.value in result.warnings


async def test_speech_is_transcribed_and_is_not_flagged_no_speech() -> None:
    jobs = _mod("transcribe_engine.domain.jobs")
    fakes_asr = _mod("tests.fakes.asr")
    job = _job()
    plan = _plan(job)
    _store, make_uow = await _seeded(job, plan)
    asr = fakes_asr.FakeASR(script=_script(plan))

    result = await _process(make_uow, asr)(job)

    assert sum(asr.calls.values()) == len(plan), (
        "every speech chunk is transcribed (positive control)"
    )
    assert result.to == jobs.JobState.COMPLETED
    assert jobs.Warning.NO_SPEECH.value not in result.warnings
