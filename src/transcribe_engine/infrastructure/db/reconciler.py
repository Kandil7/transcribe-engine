"""Postgres reconciler (S06): expires dead leases, requeues due retries, one transaction.

Expiry goes through domain transition() (LEASE_EXPIRED): retry while attempts remain, otherwise
POISON_JOB. Every comparison uses database time (D-020). Backoff comes from the domain
function and is applied as an offset from now().
"""

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from transcribe_engine.application.ports.queue import ReconcileReport
from transcribe_engine.domain.jobs import JobEvent, JobState, backoff, transition
from transcribe_engine.infrastructure.db.outbox import record_terminal_event
from transcribe_engine.infrastructure.db.session import SYSTEM_SCOPE
from transcribe_engine.infrastructure.db.uow import translate_db_error

__all__ = ["SqlReconciler"]

_LOCK_EXPIRED = text(
    """
    SELECT id, state, attempt_count, max_attempts FROM jobs
    WHERE lease_owner IS NOT NULL AND lease_until <= now()
      AND state IN ('PROCESSING', 'PENDING_VALIDATION')
    FOR UPDATE SKIP LOCKED
    """
)

_RETRY_SCHEDULED = text(
    """
    UPDATE jobs SET state = 'RETRY_SCHEDULED',
        run_after = now() + make_interval(secs => :delay_seconds),
        lease_owner = NULL, lease_until = NULL
    WHERE id = :job_id AND state = 'PROCESSING'
    """
)

_POISON = text(
    """
    UPDATE jobs SET state = 'FAILED', error_code = 'POISON_JOB',
        lease_owner = NULL, lease_until = NULL
    WHERE id = :job_id AND state IN ('PROCESSING', 'PENDING_VALIDATION')
    """
)

_CLEAR_LEASE = text("UPDATE jobs SET lease_owner = NULL, lease_until = NULL WHERE id = :job_id")

_REQUEUE_DUE = text(
    """
    UPDATE jobs SET state = 'QUEUED', run_after = NULL
    WHERE state = 'RETRY_SCHEDULED' AND run_after <= now()
    RETURNING id
    """
)


class SqlReconciler:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        backoff_base: timedelta = timedelta(seconds=30),
        backoff_cap: timedelta = timedelta(minutes=10),
        jitter: float = 0.2,
    ) -> None:
        self._engine = engine
        self._base = backoff_base
        self._cap = backoff_cap
        self._jitter = jitter

    async def run_once(self, now: datetime | None = None) -> ReconcileReport:
        """Comparisons use database time; `now` is accepted for the port and ignored (D-020)."""
        try:
            async with self._engine.begin() as conn:
                await conn.execute(SYSTEM_SCOPE)
                expired = (await conn.execute(_LOCK_EXPIRED)).all()
                poisoned = 0
                for row in expired:
                    if row.state != JobState.PROCESSING.value:
                        # A validation lease that lapses counts against the attempt limit (D-022).
                        if row.attempt_count >= row.max_attempts:
                            poisoned += 1
                            await conn.execute(_POISON, {"job_id": row.id})
                            await record_terminal_event(conn, row.id, JobState.FAILED.value)
                        else:
                            await conn.execute(_CLEAR_LEASE, {"job_id": row.id})
                        continue
                    decision = transition(
                        JobState.PROCESSING,
                        JobEvent.LEASE_EXPIRED,
                        attempt_count=row.attempt_count,
                        max_attempts=row.max_attempts,
                    )
                    if decision.to == JobState.FAILED:
                        poisoned += 1
                        await conn.execute(_POISON, {"job_id": row.id})
                        await record_terminal_event(conn, row.id, JobState.FAILED.value)
                        continue
                    delay = backoff(
                        row.attempt_count, base=self._base, cap=self._cap, jitter=self._jitter
                    )
                    await conn.execute(
                        _RETRY_SCHEDULED,
                        {"job_id": row.id, "delay_seconds": delay.total_seconds()},
                    )
                requeued = len((await conn.execute(_REQUEUE_DUE)).all())
        except SQLAlchemyError as exc:
            raise translate_db_error(exc) from exc
        return ReconcileReport(
            leases_expired=len(expired), poisoned=poisoned, retries_requeued=requeued
        )
