"""Spans per pipeline stage, linked to the job by `job_id` (S20, design: المراقبة).

A span is a pair of log records, `span.start` (DEBUG) and `span.end` (INFO), each with `job_id`,
`stage`, and on the end record `status` (ok or error) and `duration_ms`. An OpenTelemetry exporter
can replace the log sink without changing callers (see D-052).
"""

import logging
import time
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager

__all__ = ["LogTracer", "stage_span"]

_log = logging.getLogger("transcribe_engine.trace")


class LogTracer:
    """The Tracer port over the log sink: one span per stage (S20)."""

    def span(self, job_id: str, stage: str) -> AbstractContextManager[None]:
        return stage_span(job_id, stage)


@contextmanager
def stage_span(job_id: str, stage: str) -> Generator[None]:
    started = time.perf_counter()
    _log.debug("span.start", extra={"job_id": job_id, "stage": stage})
    status = "ok"
    try:
        yield
    except BaseException:
        status = "error"
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        _log.info(
            "span.end",
            extra={"job_id": job_id, "stage": stage, "status": status, "duration_ms": duration_ms},
        )
