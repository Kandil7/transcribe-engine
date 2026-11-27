"""Port for stage spans (S20).

The application opens a span per stage; the adapter decides where it goes.

A span is a context manager. It closes with status ok, or error when the stage raises.
"""

from contextlib import AbstractContextManager, nullcontext
from typing import Protocol

__all__ = ["Tracer", "open_span"]


class Tracer(Protocol):
    def span(self, job_id: str, stage: str) -> AbstractContextManager[None]: ...


def open_span(tracer: Tracer | None, job_id: str, stage: str) -> AbstractContextManager[None]:
    """The span for a stage, or a no-op when no tracer is wired (S20)."""
    if tracer is None:
        return nullcontext()
    return tracer.span(job_id, stage)
