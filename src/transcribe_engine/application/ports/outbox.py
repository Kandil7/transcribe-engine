"""Outbox, webhook secret and webhook sender ports (S20). Infrastructure and fakes implement them.

The publisher is the only caller. It delivers at least once: a row is marked delivered only after
a 2xx answer, so a crash between send and mark sends the event again. Receivers dedupe on the
event's job_id and event name.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

__all__ = ["OutboxRow", "OutboxStore", "WebhookSecrets", "WebhookSender"]


@dataclass(frozen=True)
class OutboxRow:
    id: int
    event: str
    payload: dict[str, Any]
    created_at: datetime
    attempts: int


class OutboxStore(Protocol):
    async def claim_due(self, now: datetime, limit: int) -> list[OutboxRow]:
        """Rows neither delivered nor abandoned whose next attempt is due (or never set)."""
        ...

    async def mark_delivered(self, row_id: int, now: datetime) -> None: ...

    async def reschedule(self, row_id: int, attempts: int, next_attempt_at: datetime) -> None: ...

    async def abandon(self, row_id: int, now: datetime) -> None: ...


class WebhookSecrets(Protocol):
    async def active_secrets(self, tenant_id: str) -> tuple[bytes, ...]:
        """Up to two secrets that may sign for this tenant during rotation (D-048)."""
        ...


class WebhookSender(Protocol):
    async def send(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        """POST the body and return the HTTP status. TransientError for transport failures."""
        ...
