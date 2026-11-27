"""Port for stage spans (S20).

The application opens a span per stage; the adapter decides where it goes.

A span is a context manager. It closes with status ok, or error when the stage raises.
"""

from contextlib import AbstractContextManager
from typing import Protocol

__all__ = ["Tracer"]


class Tracer(Protocol):
    def span(self, job_id: str, stage: str) -> AbstractContextManager[None]: ...
