"""In-memory job queue and reconciler (S06): the same rules as Postgres, driven by a FakeClock.

Claim order: priority (high first), then insertion order. Leases expire at `until`.
"""

from dataclasses import replace
from datetime import datetime, timedelta

from tests.fakes.clock import FakeClock
from tests.fakes.repositories import FakeStore
from transcribe_engine.application.ports.queue import Lease, ReconcileReport
from transcribe_engine.domain.errors import JobCancelledError, LeaseLostError
from transcribe_engine.domain.jobs import (
    ErrorCode,
    JobEvent,
    JobStage,
    JobState,
    Transition,
    backoff,
    transition,
)

__all__ = ["FakeJobQueue", "FakeReconciler"]


class FakeJobQueue:
    def __init__(self, store: FakeStore, clock: FakeClock) -> None:
        self._store = store
        self._clock = clock

    async def claim(
        self, queue: str, owner: str, lease_for: timedelta
    ) -> tuple[object, Lease] | None:
        now = self._clock.now()
        candidates = [
            job
            for job in self._store.jobs.values()
            if job.queue == queue
            and (job.run_after is None or job.run_after <= now)
            and job.attempt_count < job.max_attempts
            and (
                job.state == JobState.QUEUED
                or (job.state == JobState.PENDING_VALIDATION and queue == "cpu")
            )
        ]
        if not candidates:
            return None
        picked = max(enumerate(candidates), key=lambda pair: (pair[1].priority, -pair[0]))[1]
        if picked.state == JobState.QUEUED:
            picked = replace(picked, state=JobState.PROCESSING)
        picked = replace(picked, attempt_count=picked.attempt_count + 1)
        self._store.jobs[picked.id] = picked
        lease = Lease(
            job_id=picked.id, owner=owner, attempt=picked.attempt_count, until=now + lease_for
        )
        self._store.leases[picked.id] = lease
        return picked, lease

    async def heartbeat(self, lease: Lease, extend_by: timedelta) -> Lease:
        job = self._store.jobs.get(lease.job_id)
        if job is not None and job.state == JobState.CANCELLED:
            raise JobCancelledError("job was cancelled")
        current = self._store.leases.get(lease.job_id)
        now = self._clock.now()
        if (
            current is None
            or current.owner != lease.owner
            or current.attempt != lease.attempt
            or current.until <= now
        ):
            raise LeaseLostError("lease is no longer held")
        renewed = Lease(
            job_id=lease.job_id, owner=lease.owner, attempt=lease.attempt, until=now + extend_by
        )
        self._store.leases[lease.job_id] = renewed
        return renewed

    async def complete(self, lease: Lease, t: Transition, *, stage: JobStage | None = None) -> bool:
        current = self._store.leases.get(lease.job_id)
        job = self._store.jobs.get(lease.job_id)
        if (
            current is None
            or job is None
            or current.owner != lease.owner
            or current.attempt != lease.attempt
            or job.state not in (JobState.PROCESSING, JobState.PENDING_VALIDATION)
            or current.until <= self._clock.now()
        ):
            return False
        self._store.jobs[lease.job_id] = replace(
            job,
            state=t.to,
            error_code=t.error_code,
            stage=stage or job.stage,
            warnings=t.warnings,
            queue="gpu" if t.to is JobState.QUEUED else job.queue,
        )
        del self._store.leases[lease.job_id]
        return True

    async def is_cancelled(self, job_id: str) -> bool:
        job = self._store.jobs.get(job_id)
        return job is not None and job.state == JobState.CANCELLED


class FakeReconciler:
    def __init__(
        self,
        store: FakeStore,
        clock: FakeClock,
        *,
        backoff_base: timedelta = timedelta(seconds=30),
        backoff_cap: timedelta = timedelta(minutes=10),
        jitter: float = 0.0,
    ) -> None:
        self._store = store
        self._clock = clock
        self._base = backoff_base
        self._cap = backoff_cap
        self._jitter = jitter

    async def run_once(self, now: datetime | None = None) -> ReconcileReport:
        current = self._clock.now()
        expired = poisoned = 0
        for job_id, lease in list(self._store.leases.items()):
            if lease.until > current:
                continue
            del self._store.leases[job_id]
            expired += 1
            job = self._store.jobs[job_id]
            if job.state == JobState.PENDING_VALIDATION:
                # Validation leases count against the attempt limit too (D-022).
                if job.attempt_count >= job.max_attempts:
                    poisoned += 1
                    self._store.jobs[job_id] = replace(
                        job, state=JobState.FAILED, error_code=ErrorCode.POISON_JOB
                    )
                continue
            if job.state != JobState.PROCESSING:
                continue
            t = transition(
                job.state,
                JobEvent.LEASE_EXPIRED,
                attempt_count=job.attempt_count,
                max_attempts=job.max_attempts,
            )
            if t.to == JobState.FAILED:
                poisoned += 1
                self._store.jobs[job_id] = replace(job, state=t.to, error_code=t.error_code)
            else:
                delay = backoff(
                    job.attempt_count, base=self._base, cap=self._cap, jitter=self._jitter
                )
                self._store.jobs[job_id] = replace(job, state=t.to, run_after=current + delay)
        requeued = 0
        for job_id, job in list(self._store.jobs.items()):
            if (
                job.state == JobState.RETRY_SCHEDULED
                and job.run_after is not None
                and job.run_after <= current
            ):
                due = transition(
                    job.state,
                    JobEvent.RETRY_DUE,
                    attempt_count=job.attempt_count,
                    max_attempts=job.max_attempts,
                )
                self._store.jobs[job_id] = replace(job, state=due.to, run_after=None)
                requeued += 1
        return ReconcileReport(leases_expired=expired, poisoned=poisoned, retries_requeued=requeued)
