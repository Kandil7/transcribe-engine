"""Outbox rows and the publisher's store (S20, design: دورة الطلب 8).

`record_terminal_event` is the only writer of outbox rows. Every path that moves a job to
COMPLETED or FAILED calls it on the same connection as the state change, so the event exists if
and only if the state change commits (AC-1). The publisher reads through `SqlOutboxStore` in the
system scope, and reads secrets through `SqlWebhookSecrets` for one tenant.
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from transcribe_engine.application.ports.outbox import OutboxRow
from transcribe_engine.domain.events import OutboxEvent
from transcribe_engine.infrastructure.db.session import SYSTEM_SCOPE

__all__ = ["SqlOutboxStore", "SqlWebhookSecrets", "record_terminal_event"]

# Two active secrets at most while a tenant rotates (D-048).
_ACTIVE_SECRETS_LIMIT = 2

_EVENT_FOR_STATE = {
    "COMPLETED": OutboxEvent.TRANSCRIPT_COMPLETED,
    "FAILED": OutboxEvent.TRANSCRIPT_FAILED,
}

# The payload carries what the publisher needs and no transcript content (logs and payloads never
# hold text from the audio). The destination is copied from the job at write time.
_INSERT_EVENT = text(
    """
    INSERT INTO outbox (event, payload)
    SELECT CAST(:event AS text), jsonb_build_object(
        'event', CAST(:event AS text),
        'job_id', id,
        'tenant_id', tenant_id,
        'webhook_url', webhook_url,
        'error_code', error_code
    )
    FROM jobs WHERE id = :job_id
    """
)


async def record_terminal_event(conn: AsyncConnection, job_id: str, to_state: str) -> None:
    """Write the outbox row for a job that just reached a terminal state. Other states write
    nothing. Call it on the connection that made the state change (AC-1)."""
    event = _EVENT_FOR_STATE.get(to_state)
    if event is None:
        return
    await conn.execute(_INSERT_EVENT, {"event": event.value, "job_id": job_id})


_CLAIM_DUE = text(
    """
    SELECT id, event, payload, created_at, attempts
    FROM outbox
    WHERE published_at IS NULL AND abandoned_at IS NULL
      AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
    ORDER BY id
    LIMIT :limit
    FOR UPDATE SKIP LOCKED
    """
)


class SqlOutboxStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim_due(self, now: datetime, limit: int) -> list[OutboxRow]:
        async with self._engine.begin() as conn:
            await conn.execute(SYSTEM_SCOPE)
            rows = (await conn.execute(_CLAIM_DUE, {"now": now, "limit": limit})).all()
        return [
            OutboxRow(
                id=row.id,
                event=row.event,
                payload=dict(row.payload),
                created_at=row.created_at,
                attempts=row.attempts,
            )
            for row in rows
        ]

    async def mark_delivered(self, row_id: int, now: datetime) -> None:
        await self._update(
            "UPDATE outbox SET published_at = :now WHERE id = :id",
            {"now": now, "id": row_id},
        )

    async def reschedule(self, row_id: int, attempts: int, next_attempt_at: datetime) -> None:
        await self._update(
            "UPDATE outbox SET attempts = :attempts, next_attempt_at = :next WHERE id = :id",
            {"attempts": attempts, "next": next_attempt_at, "id": row_id},
        )

    async def abandon(self, row_id: int, now: datetime) -> None:
        await self._update(
            "UPDATE outbox SET abandoned_at = :now WHERE id = :id AND published_at IS NULL",
            {"now": now, "id": row_id},
        )

    async def _update(self, statement: str, params: dict[str, object]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(SYSTEM_SCOPE)
            await conn.execute(text(statement), params)


class SqlWebhookSecrets:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def active_secrets(self, tenant_id: str) -> tuple[bytes, ...]:
        async with self._engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": tenant_id},
            )
            rows = (
                await conn.execute(
                    text(
                        "SELECT secret FROM webhook_secrets "
                        "WHERE tenant_id = :tenant AND retired_at IS NULL "
                        "ORDER BY created_at DESC LIMIT :limit"
                    ),
                    {"tenant": tenant_id, "limit": _ACTIVE_SECRETS_LIMIT},
                )
            ).all()
        return tuple(bytes(row.secret) for row in rows)
