"""Outbox rows and the publisher's store (S20, design: دورة الطلب 8, D-049, D-053).

`record_terminal_event` is the only writer of outbox rows. Every path that moves a job to a terminal
state calls it on the same connection as the state change, so the event exists if and only if the
state change commits (AC-1). Jobs without a webhook get no row.

The publisher leases rows (`claim_due`) and writes each result only while it still holds the lease,
so two publishers cannot both count an attempt for the same row.
"""

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from transcribe_engine.application.ports.outbox import OutboxRow
from transcribe_engine.domain.events import event_for_state
from transcribe_engine.infrastructure.db.session import SYSTEM_SCOPE
from transcribe_engine.infrastructure.observability.metrics import JOB_OUTCOMES

__all__ = ["SqlOutboxStore", "SqlWebhookSecrets", "record_terminal_event"]

# Two active secrets at most while a tenant rotates (D-048).
_ACTIVE_SECRETS_LIMIT = 2

# The payload carries what the publisher needs and no transcript content. The destination is copied
# from the job at write time, so the publisher never reads the jobs table.
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
    FROM jobs WHERE id = :job_id AND webhook_url IS NOT NULL
    """
)


async def record_terminal_event(conn: AsyncConnection, job_id: str, to_state: str) -> None:
    """Write the outbox row for a job that just reached a terminal state, if the job has a webhook.
    Other states write nothing. Call it on the connection that made the state change (AC-1)."""
    event = event_for_state(to_state)
    if event is None:
        return
    await conn.execute(_INSERT_EVENT, {"event": event.value, "job_id": job_id})
    # Counted on the write, before commit: a rolled-back outcome is over-counted by a little.
    JOB_OUTCOMES.labels(outcome=to_state).inc()


_CLAIM_DUE = text(
    """
    UPDATE outbox SET
        lease_owner = :owner,
        lease_until = CAST(:now AS timestamptz) + make_interval(secs => :lease_seconds)
    WHERE id IN (
        SELECT id FROM outbox
        WHERE published_at IS NULL AND abandoned_at IS NULL
          AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
          AND (lease_until IS NULL OR lease_until <= :now)
        ORDER BY id
        LIMIT :limit
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id, event, payload, created_at, attempts
    """
)


class SqlOutboxStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim_due(
        self, now: datetime, limit: int, owner: str, lease_for: timedelta
    ) -> list[OutboxRow]:
        async with self._engine.begin() as conn:
            await conn.execute(SYSTEM_SCOPE)
            rows = (
                await conn.execute(
                    _CLAIM_DUE,
                    {
                        "now": now,
                        "limit": limit,
                        "owner": owner,
                        "lease_seconds": lease_for.total_seconds(),
                    },
                )
            ).all()
        return [
            OutboxRow(
                id=row.id,
                event=row.event,
                payload=dict(row.payload),
                created_at=row.created_at,
                attempts=row.attempts,
            )
            for row in sorted(rows, key=lambda r: r.id)
        ]

    async def mark_delivered(self, row_id: int, owner: str, now: datetime) -> None:
        await self._fenced(
            "UPDATE outbox SET published_at = :now, lease_owner = NULL, lease_until = NULL "
            "WHERE id = :id AND lease_owner = :owner",
            {"now": now, "id": row_id, "owner": owner},
        )

    async def reschedule(self, row_id: int, owner: str, next_attempt_at: datetime) -> None:
        await self._fenced(
            "UPDATE outbox SET attempts = attempts + 1, next_attempt_at = :next, "
            "lease_owner = NULL, lease_until = NULL WHERE id = :id AND lease_owner = :owner",
            {"next": next_attempt_at, "id": row_id, "owner": owner},
        )

    async def abandon(self, row_id: int, owner: str, now: datetime) -> None:
        await self._fenced(
            "UPDATE outbox SET abandoned_at = :now, lease_owner = NULL, lease_until = NULL "
            "WHERE id = :id AND lease_owner = :owner AND published_at IS NULL",
            {"now": now, "id": row_id, "owner": owner},
        )

    async def _fenced(self, statement: str, params: dict[str, object]) -> None:
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
