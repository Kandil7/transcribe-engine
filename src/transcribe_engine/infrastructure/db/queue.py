"""Postgres job queue (S06): claims, heartbeats and fenced completes on the jobs table.

Every time comparison uses the database clock (now()) so workers and the reconciler agree (D-020).
The claim is one statement: FOR UPDATE SKIP LOCKED picks a row, the UPDATE takes the lease.
"""

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from transcribe_engine.application.ports.queue import Lease
from transcribe_engine.domain.jobs import Job
from transcribe_engine.infrastructure.db.repositories import job_from_row

__all__ = ["SqlJobQueue"]

# Claimable: QUEUED on any queue; PENDING_VALIDATION on cpu, whose state is kept (ADR-0006).
# A retry is claimable only when its run_after has passed (database time).
_CLAIM = text(
    """
    WITH picked AS (
        SELECT id FROM jobs
        WHERE queue = :queue
          AND (state = 'QUEUED' OR (state = 'PENDING_VALIDATION' AND :queue = 'cpu'))
          AND (run_after IS NULL OR run_after <= now())
        ORDER BY priority DESC, seq
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE jobs SET
        state = CASE WHEN jobs.state = 'QUEUED' THEN 'PROCESSING' ELSE jobs.state END,
        attempt_count = jobs.attempt_count + 1,
        lease_owner = :owner,
        lease_until = now() + make_interval(secs => :lease_seconds),
        started_at = COALESCE(jobs.started_at, now())
    FROM picked
    WHERE jobs.id = picked.id
    RETURNING jobs.*
    """
)


class SqlJobQueue:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(self, queue: str, owner: str, lease_for: timedelta) -> tuple[Job, Lease] | None:
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    _CLAIM,
                    {
                        "queue": queue,
                        "owner": owner,
                        "lease_seconds": lease_for.total_seconds(),
                    },
                )
            ).one_or_none()
        if row is None:
            return None
        job = job_from_row(row)
        lease = Lease(job_id=job.id, owner=owner, attempt=job.attempt_count, until=row.lease_until)
        return job, lease
