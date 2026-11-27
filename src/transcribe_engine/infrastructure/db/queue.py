"""Postgres job queue (S06): claims, heartbeats and fenced completes on the jobs table.

Every time comparison uses the database clock (now()) so workers and the reconciler agree (D-020).
The claim is one statement: FOR UPDATE SKIP LOCKED picks a row, the UPDATE takes the lease.
"""

import json
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from transcribe_engine.application.ports.queue import Lease
from transcribe_engine.domain.errors import JobCancelledError, LeaseLostError
from transcribe_engine.domain.jobs import Job, JobStage, JobState, Transition
from transcribe_engine.infrastructure.db.outbox import record_terminal_event
from transcribe_engine.infrastructure.db.repositories import job_from_row
from transcribe_engine.infrastructure.db.session import SYSTEM_SCOPE
from transcribe_engine.infrastructure.db.uow import translate_db_error
from transcribe_engine.infrastructure.observability.metrics import JOB_FAILURES, QUEUE_WAIT_SECONDS

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
          AND attempt_count < max_attempts
          AND deletion_requested_at IS NULL
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
    RETURNING jobs.*,
        EXTRACT(EPOCH FROM (now() - jobs.created_at)) AS queue_wait_seconds
    """
)


# Heartbeat: only the current owner of the current attempt, while the lease is live and the job
# is not cancelled. The state predicate keeps a cancelled job from being renewed.
_HEARTBEAT = text(
    """
    UPDATE jobs SET lease_until = now() + make_interval(secs => :lease_seconds)
    WHERE id = :job_id AND lease_owner = :owner AND attempt_count = :attempt
      AND lease_until > now() AND state IN ('PROCESSING', 'PENDING_VALIDATION')
    RETURNING lease_until
    """
)

# Fenced complete: the write applies only while owner and attempt still match (D-019 style CAS).
# A handoff to QUEUED switches the job to the gpu queue (ADR-0006).
_COMPLETE = text(
    """
    UPDATE jobs SET
        state = :to_state,
        error_code = :error_code,
        stage = COALESCE(:stage, stage),
        queue = CASE WHEN :to_state = 'QUEUED' THEN 'gpu' ELSE queue END,
        warnings = CAST(:warnings AS jsonb),
        lease_owner = NULL,
        lease_until = NULL
    WHERE id = :job_id AND lease_owner = :owner AND attempt_count = :attempt
      AND lease_until > now() AND state IN ('PROCESSING', 'PENDING_VALIDATION')
    """
)

_STATE_OF = text("SELECT state FROM jobs WHERE id = :job_id")


async def complete_in(
    conn: AsyncConnection, lease: Lease, t: Transition, *, stage: JobStage | None = None
) -> bool:
    """The fenced complete on the caller's connection and transaction (S20, AC-1): the state change
    and its outbox row commit together, or neither does. The caller sets the system scope."""
    result = await conn.execute(
        _COMPLETE,
        {
            "to_state": t.to.value,
            "error_code": t.error_code.value if t.error_code else None,
            "stage": stage.value if stage else None,
            "warnings": json.dumps(list(t.warnings)),
            "job_id": lease.job_id,
            "owner": lease.owner,
            "attempt": lease.attempt,
        },
    )
    applied = bool(result.rowcount == 1)
    if applied:
        await record_terminal_event(conn, lease.job_id, t.to.value)
        if t.to is JobState.FAILED:
            JOB_FAILURES.labels(error_code=t.error_code.value if t.error_code else "NONE").inc()
    return applied


class SqlJobQueue:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(self, queue: str, owner: str, lease_for: timedelta) -> tuple[Job, Lease] | None:
        try:
            return await self._claim(queue, owner, lease_for)
        except SQLAlchemyError as exc:
            raise translate_db_error(exc) from exc

    async def _claim(
        self, queue: str, owner: str, lease_for: timedelta
    ) -> tuple[Job, Lease] | None:
        async with self._engine.begin() as conn:
            await conn.execute(SYSTEM_SCOPE)
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
        if job.attempt_count == 1:  # only the first claim is a queue wait; a retry is not (S20)
            QUEUE_WAIT_SECONDS.labels(queue=queue).observe(float(row.queue_wait_seconds))
        lease = Lease(job_id=job.id, owner=owner, attempt=job.attempt_count, until=row.lease_until)
        return job, lease

    async def heartbeat(self, lease: Lease, extend_by: timedelta) -> Lease:
        try:
            async with self._engine.begin() as conn:
                await conn.execute(SYSTEM_SCOPE)
                row = (
                    await conn.execute(
                        _HEARTBEAT,
                        {
                            "lease_seconds": extend_by.total_seconds(),
                            "job_id": lease.job_id,
                            "owner": lease.owner,
                            "attempt": lease.attempt,
                        },
                    )
                ).one_or_none()
                state = None
                if row is None:
                    state = (
                        await conn.execute(_STATE_OF, {"job_id": lease.job_id})
                    ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise translate_db_error(exc) from exc
        if row is not None:
            return Lease(
                job_id=lease.job_id, owner=lease.owner, attempt=lease.attempt, until=row.lease_until
            )
        if state == "CANCELLED":
            raise JobCancelledError("job was cancelled")
        raise LeaseLostError("lease is no longer held")

    async def complete(self, lease: Lease, t: Transition, *, stage: JobStage | None = None) -> bool:
        try:
            async with self._engine.begin() as conn:
                await conn.execute(SYSTEM_SCOPE)
                return await complete_in(conn, lease, t, stage=stage)
        except SQLAlchemyError as exc:
            raise translate_db_error(exc) from exc

    async def is_cancelled(self, job_id: str) -> bool:
        try:
            async with self._engine.begin() as conn:
                await conn.execute(SYSTEM_SCOPE)
                state = (await conn.execute(_STATE_OF, {"job_id": job_id})).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise translate_db_error(exc) from exc
        return state == "CANCELLED"
