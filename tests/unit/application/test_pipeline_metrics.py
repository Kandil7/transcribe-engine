"""S20 (design: monitoring): the pipeline reports its segment counts and its stage real-time factor.

Two metrics the design names, recorded where the work happens: transcribe_segments (segments
produced) and transcribe_stage_rtf (processing time over audio duration, per stage). A speech file
records its segments and one ASR stage time. Positive control: the counts are not zero for a speech
file. Negative control: an empty file records no segments.
"""

import importlib
from types import ModuleType

from tests.unit.application.test_process_job import _job, _plan, _process, _script, _seeded


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def test_segments_are_counted_for_a_speech_file() -> None:
    fake_metrics = _mod("tests.fakes.metrics").FakeMetrics()
    fakes_asr = _mod("tests.fakes.asr")
    job = _job()
    plan = _plan(job)
    _store, make_uow = await _seeded(job, plan)
    asr = fakes_asr.FakeASR(script=_script(plan))

    await _process(make_uow, asr, metrics=fake_metrics)(job)

    assert fake_metrics.segments > 0


async def test_an_empty_file_records_no_segments() -> None:
    fake_metrics = _mod("tests.fakes.metrics").FakeMetrics()
    fakes_asr = _mod("tests.fakes.asr")
    job = _job()
    _store, make_uow = await _seeded(job, ())

    await _process(make_uow, fakes_asr.FakeASR(script={}), metrics=fake_metrics)(job)

    assert fake_metrics.segments == 0


async def test_the_asr_stage_time_is_observed_once() -> None:
    fake_metrics = _mod("tests.fakes.metrics").FakeMetrics()
    fakes_asr = _mod("tests.fakes.asr")
    clock = _mod("tests.fakes.clock").FakeClock()
    job = _job()
    plan = _plan(job)
    _store, make_uow = await _seeded(job, plan)
    asr = fakes_asr.FakeASR(script=_script(plan))

    await _process(make_uow, asr, metrics=fake_metrics, clock=clock)(job)

    assert [stage for stage, _ in fake_metrics.rtf] == ["asr"]
