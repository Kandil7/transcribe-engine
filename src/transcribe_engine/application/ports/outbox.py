"""Outbox, webhook secret and webhook sender ports (S20). Infrastructure and fakes implement them.

The publisher is the only caller. It delivers at least once: a row is marked delivered only after
a 2xx answer, so a crash between send and mark sends the event again. Receivers dedupe on the
event's job_id and event name.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

__all__ = ["OutboxRow", "OutboxStore", "Resolver", "WebhookSecrets", "WebhookSender"]


@dataclass(frozen=True)
class OutboxRow:
    id: int
    event: str
    payload: dict[str, Any]
    created_at: datetime
    attempts: int


class OutboxStore(Protocol):
    """Leased, fenced access to outbox rows. A claim sets the owner and a lease; every later write
    names the owner and applies only while it still holds the row (D-053)."""

    async def claim_due(
        self, now: datetime, limit: int, owner: str, lease_for: timedelta
    ) -> list[OutboxRow]:
        """Lease up to `limit` rows that are neither delivered nor abandoned, whose next attempt is
        due (or never set), and whose lease is free or expired."""
        ...

    async def mark_delivered(self, row_id: int, owner: str, now: datetime) -> None: ...

    async def reschedule(self, row_id: int, owner: str, next_attempt_at: datetime) -> None:
        """Count one failed attempt and set when the next one is due."""
        ...

    async def abandon(self, row_id: int, owner: str, now: datetime) -> None: ...


class WebhookSecrets(Protocol):
    async def active_secrets(self, tenant_id: str) -> tuple[bytes, ...]:
        """Up to two secrets that may sign for this tenant during rotation (D-048)."""
        ...


class Resolver(Protocol):
    def resolve(self, host: str) -> Sequence[str]:
        """Every address the name resolves to. Empty means it does not resolve (not public)."""
        ...


class WebhookSender(Protocol):
    async def send(self, url: str, body: bytes, headers: Mapping[str, str], address: str) -> int:
        """POST the body to `address`, the IP the publisher verified (DNS rebinding, AC-3).

        The URL's host stays the Host header and the TLS name. Returns the HTTP status.
        TransientError for transport failures."""
        ...
