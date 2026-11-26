"""System clock adapter for the Clock port (S08). Application code gets time through the port."""

from datetime import UTC, datetime

__all__ = ["SystemClock"]


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
