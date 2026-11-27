"""S20 tracing: ProcessJob opens one span per stage, linked by job_id.

Spans exist for the ASR and PERSISTING stages of a completed job.

Positive control: both spans close with status ok.
"""

import importlib
from types import ModuleType

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
