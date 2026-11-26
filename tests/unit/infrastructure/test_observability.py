"""S20 observability on fakes: AC-5 (no transcript text in logs), tracing spans per stage, and AC-6
(every required metric is registered).

Each check has a positive control: the logs must carry the job id and the stage, the spans must
carry their end record, and the metric list must match a registry that is not empty.
Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
import io
import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from types import ModuleType
from typing import Any

import pytest

MARKER = "ZEBRA-MARKER-7Q"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


@contextmanager
def _captured_json_logs() -> Generator[io.StringIO]:
    logging_mod = _mod("transcribe_engine.infrastructure.observability.logging")
    buffer = io.StringIO()
    handler = logging_mod.json_handler(buffer)
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield buffer
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


def _records(buffer: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


async def test_no_transcript_text_in_logs() -> None:
    """AC-5: a fake job whose transcript holds a marker word logs nothing containing it. Positive
    control: the marker really reaches the stored transcript, and the logs do name the job."""
    helpers = _mod("tests.unit.application.test_process_job")
    fakes_asr = _mod("tests.fakes.asr")
    merge = _mod("transcribe_engine.domain.merge")
    job = helpers._job()
    plan = helpers._plan(job)
    _, make_uow = await helpers._seeded(job, plan)
    script = {chunk.chunk_id: (merge.RawWord(MARKER, 10, 50, None),) for chunk in plan}
    asr = fakes_asr.FakeASR(script=script)

    with _captured_json_logs() as buffer:
        await helpers._process(make_uow, asr)(job)

    async with make_uow("tenant-a") as uow:
        transcript = await uow.chunks.transcript("tenant-a", job.id)
    assert MARKER in [w.text for w in transcript.words]

    logged = buffer.getvalue()
    assert logged.count("job_id") > 0
    assert job.id in logged
    assert MARKER not in logged


def test_stage_span_logs_start_and_end_with_job_id() -> None:
    """Tracing: one span per stage, linked to the job by job_id, with its duration.

    Positive control: a span that raises still records its end, with status error, and the
    exception propagates."""
    tracing = _mod("transcribe_engine.infrastructure.observability.tracing")
    with _captured_json_logs() as buffer:
        with tracing.stage_span("job-span-1", "ASR"):
            pass
        with (
            pytest.raises(ValueError, match="stage failed"),
            tracing.stage_span("job-span-2", "VAD"),
        ):
            raise ValueError("stage failed")

    records = _records(buffer)
    ok_end = [r for r in records if r.get("job_id") == "job-span-1" and r["event"] == "span.end"]
    assert len(ok_end) == 1
    assert ok_end[0]["stage"] == "ASR"
    assert ok_end[0]["status"] == "ok"
    assert ok_end[0]["duration_ms"] >= 0
    err_end = [r for r in records if r.get("job_id") == "job-span-2" and r["event"] == "span.end"]
    assert len(err_end) == 1
    assert err_end[0]["status"] == "error"


def test_required_metrics_registered() -> None:
    """AC-6: the metrics the design asks for are registered. Positive control: the registry holds
    them, and each one is a family with the expected type."""
    registry = _mod("prometheus_client").REGISTRY
    expected = {
        "transcribe_queue_depth_jobs": "gauge",
        "transcribe_queue_depth_audio_seconds": "gauge",
        "transcribe_queue_wait_seconds": "histogram",
        "transcribe_stage_rtf": "histogram",
        "transcribe_job_failures": "counter",
        "transcribe_cache_lookups": "counter",
        "transcribe_cache_hits": "counter",
        "transcribe_segments": "counter",
        "transcribe_suspect_segments": "counter",
        "transcribe_lease_expiries": "counter",
    }
    _mod("transcribe_engine.infrastructure.observability.metrics")
    families = {family.name: family.type for family in registry.collect()}
    assert len(expected) == 10
    for name, kind in expected.items():
        assert families.get(name) == kind, name
