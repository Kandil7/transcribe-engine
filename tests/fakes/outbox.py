"""In-memory outbox, webhook secrets and webhook sender for the publisher tests (S20).

The fake outbox follows the port contract: a row is due when it is neither delivered nor
abandoned and its next attempt time has passed (or was never set). `FakeSender` stamps each call
with the fake clock's time, so a test can check the exact retry schedule.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from tests.fakes.clock import FakeClock
from transcribe_engine.domain.errors import TransientError

__all__ = ["FakeOutbox", "FakeOutboxRow", "FakeSecrets", "FakeSender"]


@dataclass(frozen=True)
class FakeOutboxRow:
    id: int
    event: str
    payload: dict[str, Any]
    created_at: datetime
    attempts: int = 0
    next_attempt_at: datetime | None = None
    published_at: datetime | None = None
    abandoned_at: datetime | None = None


@dataclass
class FakeOutbox:
    rows: dict[int, FakeOutboxRow] = field(default_factory=dict)
    _next_id: int = 1

    def add(self, event: str, payload: dict[str, Any], created_at: datetime) -> int:
        row_id = self._next_id
        self._next_id += 1
        self.rows[row_id] = FakeOutboxRow(row_id, event, payload, created_at)
        return row_id

    async def claim_due(self, now: datetime, limit: int) -> list[FakeOutboxRow]:
        due = [
            row
            for row in sorted(self.rows.values(), key=lambda r: r.id)
            if row.published_at is None
            and row.abandoned_at is None
            and (row.next_attempt_at is None or row.next_attempt_at <= now)
        ]
        return due[:limit]

    async def mark_delivered(self, row_id: int, now: datetime) -> None:
        self.rows[row_id] = replace(self.rows[row_id], published_at=now)

    async def reschedule(self, row_id: int, attempts: int, next_attempt_at: datetime) -> None:
        self.rows[row_id] = replace(
            self.rows[row_id], attempts=attempts, next_attempt_at=next_attempt_at
        )

    async def abandon(self, row_id: int, now: datetime) -> None:
        self.rows[row_id] = replace(self.rows[row_id], abandoned_at=now)

    def pending_due_times(self) -> list[datetime]:
        return sorted(
            row.next_attempt_at
            for row in self.rows.values()
            if row.published_at is None and row.abandoned_at is None and row.next_attempt_at
        )


@dataclass
class FakeSecrets:
    by_tenant: dict[str, tuple[bytes, ...]] = field(default_factory=dict)

    async def active_secrets(self, tenant_id: str) -> tuple[bytes, ...]:
        return self.by_tenant.get(tenant_id, ())


@dataclass
class FakeSender:
    """Answers with the scripted statuses in order, then 200. `calls` records each attempt."""

    clock: FakeClock
    statuses: list[int] = field(default_factory=list)
    raise_transient: bool = False
    calls: list[tuple[datetime, str, bytes, dict[str, str]]] = field(default_factory=list)

    async def send(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        self.calls.append((self.clock.now(), url, body, dict(headers)))
        if self.raise_transient:
            raise TransientError("fake transport failure")
        return self.statuses.pop(0) if self.statuses else 200
