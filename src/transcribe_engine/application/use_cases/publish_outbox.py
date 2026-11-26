"""Outbox publisher (S20, D-048, D-049): delivers each due event to its webhook destination.

- At least once: a row is marked delivered only after a 2xx answer.
- Signed: one `v1=` signature per active tenant secret, over "<ts>.<body>", in one header with the
  timestamp `t=` (two secrets while a tenant rotates, D-048).
- Retried on the schedule from `retry_offsets()`, counted from the event's creation, until 24 hours;
  then the row is abandoned.
- SSRF at send time: the destination is resolved now, and refused unless https and every address is
  public (AC-3). A refused destination is abandoned, not retried, because the same name will fail
  the same way.

The body carries no webhook URL. Resolution runs in a thread, since it blocks.
"""

import asyncio
import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from transcribe_engine.application.ports.clock import Clock
from transcribe_engine.application.ports.outbox import (
    OutboxRow,
    OutboxStore,
    WebhookSecrets,
    WebhookSender,
)
from transcribe_engine.domain.errors import TransientError
from transcribe_engine.domain.webhooks import is_public_destination, retry_offsets, sign

__all__ = ["OutboxPublisher"]

BATCH_SIZE = 50
Resolve = Callable[[str], Sequence[str]]


class OutboxPublisher:
    def __init__(
        self,
        store: OutboxStore,
        secrets: WebhookSecrets,
        sender: WebhookSender,
        clock: Clock,
        resolve: Resolve,
    ) -> None:
        self._store = store
        self._secrets = secrets
        self._sender = sender
        self._clock = clock
        self._resolve = resolve

    async def run_once(self) -> int:
        """Attempt every due row once. Returns how many rows were due."""
        now = self._clock.now()
        rows = await self._store.claim_due(now, BATCH_SIZE)
        for row in rows:
            await self._deliver(row, now)
        return len(rows)

    async def _deliver(self, row: OutboxRow, now: datetime) -> None:
        url = row.payload.get("webhook_url")
        if not isinstance(url, str):
            await self._store.mark_delivered(row.id, now)  # the job had no webhook: nothing to send
            return
        host = urlsplit(url).hostname
        addresses = await asyncio.to_thread(self._resolve, host) if host else []
        if not is_public_destination(url, lambda _host: addresses):
            await self._store.abandon(row.id, now)
            return
        secrets = await self._secrets.active_secrets(str(row.payload["tenant_id"]))
        if not secrets:
            await self._retry(row, now)  # no secret yet: keep the event for a later attempt
            return
        body = _body(row)
        ts = int(now.timestamp())
        signature = f"t={ts}," + ",".join(f"v1={sign(body, s, ts)}" for s in secrets)
        headers = {
            "Content-Type": "application/json",
            "X-Transcribe-Event": row.event,
            "X-Transcribe-Signature": signature,
        }
        try:
            status = await self._sender.send(url, body, headers)
        except TransientError:
            status = 0
        if 200 <= status < 300:
            await self._store.mark_delivered(row.id, now)
        else:
            await self._retry(row, now)

    async def _retry(self, row: OutboxRow, now: datetime) -> None:
        attempts = row.attempts + 1
        offsets = retry_offsets()
        if attempts > len(offsets):
            await self._store.abandon(row.id, now)
            return
        due = row.created_at + timedelta(seconds=offsets[attempts - 1])
        await self._store.reschedule(row.id, attempts, due)


def _body(row: OutboxRow) -> bytes:
    fields = {key: value for key, value in row.payload.items() if key != "webhook_url"}
    fields["id"] = row.id
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
