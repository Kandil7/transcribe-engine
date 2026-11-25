"""Controllable clock for the fake queue (S06). Tests move time explicitly; they never sleep."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

__all__ = ["FakeClock"]


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 11, 26, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current = self.current + delta
