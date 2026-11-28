"""Outbox rows and the publisher's store (S20, design: دورة الطلب 8, D-049, D-053).

`record_terminal_event` is the only writer of outbox rows. Every path that moves a job to a terminal
state calls it on the same connection as the state change, so the event exists if and only if the
state change commits (AC-1). Jobs without a webhook get no row.

The publisher leases rows (`claim_due`) and writes each result only while it still holds the lease,
so two publishers cannot both count an attempt for the same row.
"""

import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from transcribe_engine.application.ports.outbox import OutboxRow
from transcribe_engine.domain.events import event_for_state
from transcribe_engine.infrastructure.db.session import SYSTEM_SCOPE
from transcribe_engine.infrastructure.observability.metrics import JOB_OUTCOMES
from transcribe_engine.infrastructure.security.secret_box import open_sealed, seal

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


_log = logging.getLogger(__name__)
_SECRET_ROTATION_KEEP = 2  # two active secrets while a tenant rotates (D-048)


class SqlWebhookSecrets:
    """Reads a tenant's active signing secrets, opened with the key from TE_SECRET_KEY.

    Without a key, no secret is returned: the publisher keeps the event and sends nothing
    unsigned (D-082).
    A stored secret that cannot be opened is skipped and logged without its content.
    """

    def __init__(self, engine: AsyncEngine, key: bytes | None = None) -> None:
        self._engine = engine
        self._key = key

    async def active_secrets(self, tenant_id: str) -> tuple[bytes, ...]:
        if self._key is None:
            _log.warning("webhook secret key is not set; deliveries wait until it is")
            return ()
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
        opened: list[bytes] = []
        for row in rows:
            try:
                opened.append(open_sealed(self._key, bytes(row.secret)))
            except ValueError:
                _log.warning("a stored webhook secret could not be opened; it is skipped")
        return tuple(opened)


async def add_webhook_secret(engine: AsyncEngine, key: bytes, tenant_id: str) -> str:
    """Create a new signing secret for a tenant and return it once. Only the sealed form is stored.

    Older secrets beyond the two newest are retired in the same transaction (D-082, D-048).
    """
    plaintext = secrets.token_urlsafe(32)
    secret_id = "whk_" + secrets.token_hex(8)
    sealed = seal(key, plaintext.encode("utf-8"))
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": tenant_id},
        )
        await conn.execute(
            text(
                "INSERT INTO webhook_secrets (tenant_id, secret_id, secret) "
                "VALUES (:tenant, :secret_id, :secret)"
            ),
            {"tenant": tenant_id, "secret_id": secret_id, "secret": sealed},
        )
        await conn.execute(
            text(
                "UPDATE webhook_secrets SET retired_at = now() "
                "WHERE tenant_id = :tenant AND retired_at IS NULL AND secret_id NOT IN ("
                "  SELECT secret_id FROM webhook_secrets "
                "  WHERE tenant_id = :tenant AND retired_at IS NULL "
                "  ORDER BY created_at DESC LIMIT :keep)"
            ),
            {"tenant": tenant_id, "keep": _SECRET_ROTATION_KEEP},
        )
    return plaintext
