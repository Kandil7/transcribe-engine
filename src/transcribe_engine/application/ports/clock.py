"""Clock port (S06). Application code takes time here; the Postgres queue uses database time."""

from datetime import datetime
from typing import Protocol

__all__ = ["Clock"]


class Clock(Protocol):
    def now(self) -> datetime: ...
