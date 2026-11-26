"""Outbox publisher (S20, D-048, D-049, D-053): delivers each due event to its webhook destination.

- At least once: a row is marked delivered only after a 2xx answer, and only while this publisher
  holds the row's lease (fenced writes, so two publishers never both count an attempt).
- Signed: one `v1=` signature per active tenant secret, over "<ts>.<body>", in one header with the
  timestamp `t=` (two secrets while a tenant rotates, D-048).
- Retried on the schedule from `retry_offsets()`, counted from the event's creation, until 24 hours;
  then the row is abandoned.
- SSRF at send time: the destination is resolved once, checked (https, port 443, every address
  global), and the send goes to the verified address (D-053). A refused destination is abandoned,
  not retried, because the same name would fail the same way.

The body carries no webhook URL. Resolution runs in a thread, since it blocks.
"""

import asyncio
import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from transcribe_engine.application.ports.clock import Clock
from transcribe_engine.application.ports.outbox import (
    OutboxRow,
    OutboxStore,
    Resolver,
    WebhookSecrets,
    WebhookSender,
)
from transcribe_engine.domain.errors import TransientError
from transcribe_engine.domain.webhooks import is_public_destination, retry_offsets, sign

__all__ = ["OutboxPublisher"]

BATCH_SIZE = 50
DEFAULT_LEASE = timedelta(minutes=5)


class OutboxPublisher:
    def __init__(
        self,
        store: OutboxStore,
        secrets: WebhookSecrets,
        sender: WebhookSender,
        clock: Clock,
        resolver: Resolver,
        owner: str,
    ) -> None:
        self._store = store
        self._secrets = secrets
        self._sender = sender
        self._clock = clock
        self._resolver = resolver
        self._owner = owner

    async def run_once(self) -> int:
        """Attempt every due row once. Returns how many rows were leased."""
        now = self._clock.now()
        rows = await self._store.claim_due(now, BATCH_SIZE, self._owner, DEFAULT_LEASE)
        for row in rows:
            await self._deliver(row, now)
        return len(rows)

    async def _deliver(self, row: OutboxRow, now: datetime) -> None:
        url = row.payload.get("webhook_url")
        if not isinstance(url, str):
            await self._store.mark_delivered(
                row.id, self._owner, now
            )  # no webhook: nothing to send
            return
        host = urlsplit(url).hostname
        addresses = await asyncio.to_thread(self._resolver.resolve, host) if host else []
        if not is_public_destination(url, lambda _host: addresses):
            await self._store.abandon(row.id, self._owner, now)
            return
        # Literal IPs pass the check as themselves; names pass as the address they resolved to.
        pinned = addresses[0] if addresses else str(host)
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
            status = await self._sender.send(url, body, headers, pinned)
        except TransientError:
            status = 0
        if 200 <= status < 300:
            await self._store.mark_delivered(row.id, self._owner, now)
        else:
            await self._retry(row, now)

    async def _retry(self, row: OutboxRow, now: datetime) -> None:
        attempts = row.attempts + 1
        offsets = retry_offsets()
        if attempts > len(offsets):
            await self._store.abandon(row.id, self._owner, now)
            return
        due = row.created_at + timedelta(seconds=offsets[attempts - 1])
        await self._store.reschedule(row.id, self._owner, due)


def _body(row: OutboxRow) -> bytes:
    fields = {key: value for key, value in row.payload.items() if key != "webhook_url"}
    fields["id"] = row.id
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
