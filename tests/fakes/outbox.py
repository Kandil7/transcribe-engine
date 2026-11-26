"""In-memory outbox, webhook secrets, resolver and webhook sender for the publisher tests (S20).

The fake outbox follows the port contract: a row is claimable when it is neither delivered nor
abandoned, its next attempt time has passed (or was never set), and its lease is free or expired.
Writes apply only to the owner holding the lease (D-053). `FakeSender` stamps each call with the
fake clock's time and records the pinned address, so a test can check the schedule and the pin.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from tests.fakes.clock import FakeClock
from transcribe_engine.domain.errors import TransientError

__all__ = ["FakeOutbox", "FakeOutboxRow", "FakeResolver", "FakeSecrets", "FakeSender"]


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
    lease_owner: str | None = None
    lease_until: datetime | None = None


@dataclass
class FakeOutbox:
    rows: dict[int, FakeOutboxRow] = field(default_factory=dict)
    _next_id: int = 1

    def add(self, event: str, payload: dict[str, Any], created_at: datetime) -> int:
        row_id = self._next_id
        self._next_id += 1
        self.rows[row_id] = FakeOutboxRow(row_id, event, payload, created_at)
        return row_id

    async def claim_due(
        self, now: datetime, limit: int, owner: str, lease_for: timedelta
    ) -> list[FakeOutboxRow]:
        due = [
            row
            for row in sorted(self.rows.values(), key=lambda r: r.id)
            if row.published_at is None
            and row.abandoned_at is None
            and (row.next_attempt_at is None or row.next_attempt_at <= now)
            and (row.lease_until is None or row.lease_until <= now)
        ][:limit]
        leased = []
        for row in due:
            updated = replace(row, lease_owner=owner, lease_until=now + lease_for)
            self.rows[row.id] = updated
            leased.append(updated)
        return leased

    def _held(self, row_id: int, owner: str) -> bool:
        return self.rows[row_id].lease_owner == owner

    async def mark_delivered(self, row_id: int, owner: str, now: datetime) -> None:
        if self._held(row_id, owner):
            self.rows[row_id] = replace(
                self.rows[row_id], published_at=now, lease_owner=None, lease_until=None
            )

    async def reschedule(self, row_id: int, owner: str, next_attempt_at: datetime) -> None:
        if self._held(row_id, owner):
            row = self.rows[row_id]
            self.rows[row_id] = replace(
                row,
                attempts=row.attempts + 1,
                next_attempt_at=next_attempt_at,
                lease_owner=None,
                lease_until=None,
            )

    async def abandon(self, row_id: int, owner: str, now: datetime) -> None:
        if self._held(row_id, owner):
            self.rows[row_id] = replace(
                self.rows[row_id], abandoned_at=now, lease_owner=None, lease_until=None
            )

    def next_due_time(self) -> datetime | None:
        due = self.pending_due_times()
        return due[0] if due else None

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
class FakeResolver:
    table: dict[str, list[str]] = field(default_factory=dict)

    def resolve(self, host: str) -> Sequence[str]:
        return self.table.get(host, [])


@dataclass
class FakeSender:
    """Answers with the scripted statuses in order, then 200. `calls` records each attempt as
    (sent_at, url, body, headers, pinned address)."""

    clock: FakeClock
    statuses: list[int] = field(default_factory=list)
    raise_transient: bool = False
    calls: list[tuple[datetime, str, bytes, dict[str, str], str]] = field(default_factory=list)

    async def send(self, url: str, body: bytes, headers: Mapping[str, str], address: str) -> int:
        self.calls.append((self.clock.now(), url, body, dict(headers), address))
        if self.raise_transient:
            raise TransientError("fake transport failure")
        return self.statuses.pop(0) if self.statuses else 200
